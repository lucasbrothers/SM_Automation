from __future__ import annotations

import ipaddress
import re
import shlex
from typing import Any

from core.inventory import ServerRecord
from engine.ssh import SSHClient, SSHCommandError


_DIRECTIVES = {
    "permitrootlogin": "PermitRootLogin",
    "pubkeyauthentication": "PubkeyAuthentication",
}
_VALUES = {
    "permitrootlogin": {"yes", "no", "without-password", "prohibit-password", "forced-commands-only"},
    "pubkeyauthentication": {"yes", "no"},
}


def validate_actions(actions: list[dict[str, Any]], *, require_current: bool = True) -> None:
    if not isinstance(actions, list) or not actions:
        raise ValueError("Actions must be a nonempty list")
    seen = set()
    for action in actions:
        if not isinstance(action, dict) or action.get("type") != "set_sshd_option":
            raise ValueError("Unsupported action type")
        name = action.get("parameter")
        if not isinstance(name, str) or name not in _DIRECTIVES:
            raise ValueError(f"Unsupported SSH setting for application: {name}")
        if name in seen:
            raise ValueError("Duplicate SSH setting in plan")
        seen.add(name)
        for field in ("recommended", "current") if require_current else ("recommended",):
            value = action.get(field)
            if not isinstance(value, str) or value not in _VALUES[name]:
                raise ValueError(f"SSH setting {field} contains unsupported characters or value")


def _expected(value: str) -> str:
    return "without-password" if value == "prohibit-password" else value


def _checks(actions: list[dict[str, Any]], field: str) -> str:
    checks = ['observed=$(sshd -T -f "$cfg")']
    for action in actions:
        if field not in action:
            continue
        name = action["parameter"]
        expected = _expected(action[field])
        checks.append(
            f"actual=$(printf '%s\\n' \"$observed\" | awk '$1 == \"{name}\" {{print $2}}')\n"
            'if [ "$actual" = prohibit-password ]; then actual=without-password; fi\n'
            f'[ "$actual" = {shlex.quote(expected)} ] || {{ echo "SSH {field} mismatch: {name}" >&2; exit 1; }}'
        )
    return "\n".join(checks)


def build_sshd_apply_batch_command(actions: list[dict[str, Any]]) -> str:
    """One Linux transaction; refuse conditional or included configuration.

    The original file is backed up once, before any action. Failed writes,
    validation, reload or effective-value checks restore that original file.
    """
    validate_actions(actions, require_current=False)
    # Validate supplied preconditions even for the single-setting convenience API.
    for action in actions:
        if "current" in action:
            validate_actions([action])
    desired = "".join(f'{_DIRECTIVES[a["parameter"]]} {a["recommended"]}\n' for a in actions)
    names = "|".join(a["parameter"] for a in actions)
    script = r'''
set -eu
umask 077
cfg=/etc/ssh/sshd_config
lock=/etc/ssh/.sm_automation.lock
mkdir "$lock" || { echo 'Another apply or rollback is active; inspect lock' >&2; exit 1; }
changed=0
backup=
cleanup() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$changed" = 1 ]; then
        if cp -p "$backup" "$cfg" && sshd -t -f "$cfg" && systemctl reload sshd; then
            echo "Rolled back; backup=$backup" >&2
        else
            echo "ROLLBACK FAILED; manual recovery required; backup=$backup" >&2
        fi
        rc=1
    fi
    rmdir "$lock" || rc=1
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
[ -f "$cfg" ] && [ ! -L "$cfg" ]
# Match applies until the next Match block, and Include may contain more blocks.
# Neither can safely be rewritten by this flat-file adapter.
if awk '{key=tolower($1); sub(/=.*/, "", key)} key == "include" || key == "match" {found=1} END {exit !found}' "$cfg"; then
    echo 'Include/Match configuration requires a dedicated adapter; no changes made' >&2
    exit 1
fi
sshd -t -f "$cfg"
'''
    script += _checks(actions, "current") + "\n"
    script += r'''
backupdir=$(mktemp -d /etc/ssh/.sm_automation.XXXXXXXXXX)
backup="$backupdir/sshd_config"
cp -p "$cfg" "$backup"
candidate="$backupdir/candidate"
cp -p "$cfg" "$candidate"
'''
    script += "{ printf '%s' " + shlex.quote(desired) + ";\n"
    awk_filter = '{key=tolower($1); sub(/=.*/, "", key)} key !~ /^(' + names + ')$/ {print}'
    script += "awk " + shlex.quote(awk_filter) + ' "$cfg"; } > "$candidate"\n'
    script += r'''
sshd -t -f "$candidate"
changed=1
cat "$candidate" > "$cfg"
sshd -t -f "$cfg"
'''
    script += _checks(actions, "recommended") + "\n"
    script += "systemctl reload sshd\n" + _checks(actions, "recommended") + "\n"
    script += r'''
checksum=$(sha256sum "$cfg")
digest=${checksum%% *}
[ "${#digest}" = 64 ]
case "$digest" in *[!0-9a-f]*) exit 1 ;; esac
printf 'backup=%s\ndigest=%s\n' "$backup" "$digest"
changed=0
'''
    return "sudo -n sh -c " + shlex.quote(script)


def build_sshd_apply_command(parameter: str, value: str) -> str:
    return build_sshd_apply_batch_command([
        {"type": "set_sshd_option", "parameter": parameter, "recommended": value},
    ])


def _rollback_command(backup: str, digest: str) -> str:
    if not re.fullmatch(r"/etc/ssh/\.sm_automation\.[A-Za-z0-9]{10}/sshd_config", backup):
        raise SSHCommandError("Invalid rollback backup path")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SSHCommandError("Invalid rollback digest")
    script = r'''
set -eu
cfg=/etc/ssh/sshd_config
lock=/etc/ssh/.sm_automation.lock
mkdir "$lock"
trap 'rmdir "$lock"' EXIT
'''
    script += f'expected={shlex.quote(digest)}\nbackup={shlex.quote(backup)}\n'
    script += r'''
checksum=$(sha256sum "$cfg")
actual=${checksum%% *}
[ "$actual" = "$expected" ] || { echo 'Config changed concurrently; manual recovery required' >&2; exit 1; }
cp -p "$backup" "$cfg"
sshd -t -f "$cfg"
systemctl reload sshd
cmp -s "$backup" "$cfg"
'''
    return "sudo -n sh -c " + shlex.quote(script)


def apply_sshd_settings(client: SSHClient, actions: list[dict[str, Any]]) -> str:
    """Apply one batch and verify a fresh authenticated connection before success."""
    validate_actions(actions)
    output = client.execute(build_sshd_apply_batch_command(actions))
    metadata = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    backup, digest = metadata.get("backup", ""), metadata.get("digest", "")
    rollback = _rollback_command(backup, digest)
    probe = SSHClient(client.hostname, client.ip, user=client.user, timeout=client.timeout,
                      password=client.password, key_filename=client.key_filename, port=client.port)
    try:
        probe.execute("sudo -n true")
    except Exception as exc:
        try:
            client.execute(rollback)
        except Exception as rollback_exc:
            raise SSHCommandError(f"Reconnect failed; ROLLBACK FAILED; backup={backup}: {rollback_exc}") from exc
        raise SSHCommandError(f"Reconnect failed; original configuration restored; backup={backup}") from exc
    finally:
        probe.close()
    return output


def apply_sshd_setting(client: SSHClient, parameter: str, value: str) -> str:
    """Apply a single option with the same transaction and reconnect safeguards."""
    from security.audit import _sshd_settings

    validate_actions([{"type": "set_sshd_option", "parameter": parameter,
                       "recommended": value}], require_current=False)
    current = _sshd_settings(client.execute("sudo -n sshd -T")).get(parameter)
    return apply_sshd_settings(client, [{"type": "set_sshd_option", "parameter": parameter,
                                         "current": current, "recommended": value}])


def validate_plan(plan: object, servers: list[ServerRecord]) -> list[dict[str, Any]]:
    """Validate the entire plan before opening even the first SSH connection."""
    if not isinstance(plan, list) or not plan:
        raise ValueError("Plan must be a nonempty list")
    server_map = {server.hostname: server for server in servers}
    if len({server.hostname.casefold() for server in servers}) != len(servers):
        raise ValueError("Duplicate inventory hostname")
    seen = set()
    for record in plan:
        if not isinstance(record, dict):
            raise ValueError("Plan records must be objects")
        hostname = record.get("hostname")
        if not isinstance(hostname, str) or hostname.casefold() in seen:
            raise ValueError("Invalid or duplicate plan hostname")
        seen.add(hostname.casefold())
        server = server_map.get(hostname)
        if server is None:
            raise ValueError(f"Plan target is not in inventory: {hostname}")
        address = record.get("ip")
        if not isinstance(address, str) or ipaddress.ip_address(address) != ipaddress.ip_address(server.ip):
            raise ValueError(f"Plan IP does not match inventory: {hostname}")
        if server.os.casefold() not in {"linux", "rhel", "rhel8", "rhel9", "rhel 8", "rhel 9"}:
            raise ValueError(f"Unsupported apply platform: {server.os}")
        if record.get("scope") != "sshd_settings":
            raise ValueError("Plan scope must be sshd_settings; regenerate legacy plans")
        if not isinstance(record.get("status"), str) or record["status"] not in {"action_required", "no_changes"}:
            raise ValueError(f"Plan is blocked or has invalid status: {hostname}")
        actions = record.get("actions")
        if record["status"] == "no_changes":
            if actions != []:
                raise ValueError("no_changes records must have an empty actions list")
        else:
            validate_actions(actions)
    return plan

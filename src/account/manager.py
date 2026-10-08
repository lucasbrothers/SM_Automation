"""Linux account operations, executed only through the main server's SSH client."""
from __future__ import annotations

from datetime import date
import re
import shlex

from engine.remote import capture, privileged


def validate_options(options):
    if not isinstance(options, dict):
        raise ValueError("Account options must be an object")
    action = options.get("action", "list")
    if action not in {"list", "create", "modify", "lock", "unlock", "delete"}:
        raise ValueError("Unknown account action")
    result = {"action": action}
    if action == "list":
        return result
    username = str(options.get("username", ""))
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise ValueError("Use a Linux username of at most 32 lowercase characters")
    result["username"] = username
    if action in {"create", "modify"}:
        for field in ("sr", "full_name"):
            value = str(options.get(field, "")).strip()
            if not value or len(value) > 100 or any(ord(c) < 32 or c in ":," for c in value):
                raise ValueError("SR and full name are required; colon, comma and control characters are not allowed")
            result[field] = value
        result["comment"] = f"{result['sr']}-{date.today().isoformat()}-{result['full_name']}"
    if action == "create":
        for field in ("uid", "gid"):
            value = options.get(field)
            if value not in (None, ""):
                if isinstance(value, bool) or not str(value).isdigit() or not 1000 <= int(value) <= 2147483646:
                    raise ValueError("UID/GID must be an integer from 1000 to 2147483646")
                result[field] = int(value)
    return result


def account_command(options, login_user):
    action = options["action"]
    if action == "list":
        # Never return shadow password hashes to Windows.
        return "getent passwd"
    username = options["username"]
    if username == login_user:
        raise ValueError("The SSH management account cannot be changed")
    user = shlex.quote(username)
    prefix = "set -eu; exec 9>/run/lock/sm-automation-accounts.lock; flock -w 30 9; "
    if action == "create":
        command = f"useradd -m -s /bin/bash -c {shlex.quote(options['comment'])}"
        if "uid" in options:
            command += f" -u {options['uid']}"
        if "gid" in options:
            prefix += f"getent group {options['gid']} >/dev/null; "
            command += f" -g {options['gid']}"
        command += f" -- {user}"
        prefix += f"if getent passwd {user} >/dev/null; then echo 'Account already exists' >&2; exit 1; fi; "
    else:
        prefix += f"entry=$(getent passwd {user}); uid=$(printf '%s' \"$entry\" | cut -d: -f3); "
        prefix += "if [ \"$uid\" -lt 1000 ] || [ \"$uid\" -eq 65534 ]; then echo 'Protected system account' >&2; exit 1; fi; "
        command = {
            "modify": f"usermod -c {shlex.quote(options.get('comment', ''))} -- {user}",
            "lock": f"usermod -L -- {user}",
            "unlock": f"usermod -U -- {user}",
            "delete": f"userdel -- {user}",
        }[action]
        if action == "unlock":
            # An empty or never-set password must not become a passwordless login.
            prefix += f"hash=$(getent shadow {user} | cut -d: -f2); "
            prefix += "case \"$hash\" in '!$'*) ;; *) echo 'Unlock requires a previously set password hash' >&2; exit 1;; esac; "
    suffix = f"; getent passwd {user}; passwd -S {user}" if action != "delete" else "; echo 'Account deleted; home retained'"
    return prefix + command + suffix


def manage_accounts(client, options, mode, login_user, timeout):
    response = capture(client, privileged(account_command(options, login_user), mode), timeout=timeout, max_bytes=2 * 1024 * 1024)
    if response.exit_code:
        raise RuntimeError(response.stderr.strip() or f"Account operation exited {response.exit_code}")
    text = response.stdout.decode("utf-8", errors="replace")
    if options["action"] != "list":
        return {"action": options["action"], "username": options["username"], "output": text, "warnings": response.stderr}
    accounts = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) == 7:
            accounts.append(dict(zip(("username", "uid", "gid", "comment", "home", "shell"), (parts[0], *parts[2:]))))
    return {"action": "list", "accounts": accounts}

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
    if action not in {"list", "create", "modify", "groups", "remove_groups", "primary_group", "password_age", "expiry", "lock", "unlock", "delete", "public_key"}:
        raise ValueError("Unknown account action")
    result = {"action": action}
    if action == "list":
        return result
    username = str(options.get("username", ""))
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise ValueError("Use a Linux username of at most 32 lowercase characters")
    result["username"] = username
    if action == "public_key":
        from account.keys import validate_public_key
        result["public_key"] = validate_public_key(options.get("public_key"))
    if action == "expiry":
        value = str(options.get("expiry_date", "")).strip()
        if value == "never":
            result["expiry_date"] = "-1"
        else:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Use YYYY-MM-DD or never for account expiry")
            result["expiry_date"] = date.fromisoformat(value).isoformat()
    if action == "password_age":
        days = options.get("max_days", "")
        if isinstance(days, bool) or not str(days).isdigit() or not 1 <= int(days) <= 99999:
            raise ValueError("Password maximum age must be 1 to 99999 days")
        result["max_days"] = int(days)
    if action in {"groups", "remove_groups", "primary_group"}:
        groups = str(options.get("groups", "")).split(",")
        groups = [g.strip() for g in groups]
        if not 1 <= len(groups) <= 32 or any(not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", g) for g in groups):
            raise ValueError("Provide up to 32 existing group names separated by commas")
        result["groups"] = list(dict.fromkeys(groups))
        if action == "primary_group" and len(result["groups"]) != 1:
            raise ValueError("Choose exactly one existing primary group")
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
    if action == "public_key":
        from account.keys import key_command
        return prefix + key_command(username, "install", options["public_key"])
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
            "groups": f"usermod -a -G {shlex.quote(','.join(options.get('groups', [])))} -- {user}",
            "remove_groups": "; ".join(f"gpasswd -d {user} {shlex.quote(group)}" for group in options.get("groups", [])),
            "primary_group": f"usermod -g {shlex.quote(options.get('groups', [''])[0])} -- {user}",
            "password_age": f"chage -M {options.get('max_days', 99999)} -- {user}; LC_ALL=C chage -l {user}",
            "expiry": f"chage -E {shlex.quote(options.get('expiry_date', '-1'))} -- {user}; LC_ALL=C chage -l {user}",
        }[action]
        if action in {"groups", "remove_groups", "primary_group"}:
            for group in options["groups"]:
                prefix += f"getent group {shlex.quote(group)} >/dev/null; "
                if action == "remove_groups":
                    prefix += f"id -nG {user} | tr ' ' '\\n' | grep -Fx {shlex.quote(group)} >/dev/null; "
                    prefix += f"primary=$(id -gn {user}); [ \"$primary\" != {shlex.quote(group)} ] || {{ echo 'Cannot remove primary group' >&2; exit 1; }}; "
        if action == "unlock":
            # An empty or never-set password must not become a passwordless login.
            prefix += f"hash=$(getent shadow {user} | cut -d: -f2); "
            prefix += "case \"$hash\" in '!$'*) ;; *) echo 'Unlock requires a previously set password hash' >&2; exit 1;; esac; "
    suffix = f"; getent passwd {user}; passwd -S {user}; id -nG {user}" if action != "delete" else "; echo 'Account deleted; home retained'"
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

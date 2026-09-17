from __future__ import annotations

import re
import shlex

from engine.ssh import SSHClient


_DIRECTIVES = {
    "permitrootlogin": "PermitRootLogin",
    "pubkeyauthentication": "PubkeyAuthentication",
}


def build_sshd_apply_command(parameter: str, value: str) -> str:
    """Build a backup, validate, and reload command for one SSH setting."""
    directive = _DIRECTIVES.get(parameter)
    if directive is None:
        raise ValueError(f"Unsupported SSH setting for application: {parameter}")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("SSH setting value contains unsupported characters.")

    quoted_directive = shlex.quote(directive)
    quoted_value = shlex.quote(value)
    return (
        "sudo sh -c 'set -eu; "
        "cfg=/etc/ssh/sshd_config; "
        "backup=\"$cfg.sm_automation.$(date +%Y%m%d%H%M%S).bak\"; "
        "cp -p \"$cfg\" \"$backup\"; "
        f"if grep -Eiq \"^[[:space:]]*{quoted_directive}[[:space:]]+\" \"$cfg\"; then "
        f"sed -i -E \"s|^[[:space:]]*{quoted_directive}[[:space:]]+.*$|{directive} {value}|I\" \"$cfg\"; "
        f"else printf \"\\n{directive} {value}\\n\" >> \"$cfg\"; fi; "
        "if ! sshd -t; then cp -p \"$backup\" \"$cfg\"; exit 1; fi; "
        "systemctl reload sshd; printf \"backup=%s\\n\" \"$backup\"'"
    )


def apply_sshd_setting(
    client: SSHClient,
    parameter: str,
    value: str,
) -> str:
    """Apply one setting through the existing SSH client."""
    return client.execute(build_sshd_apply_command(parameter, value))

"""A narrow Linux policy: protect the root-owned SSH configuration file."""
from engine.remote import capture, privileged


def secure_ssh_config(client, mode, timeout):
    command = """set -eu
file=/etc/ssh/sshd_config
[ -f "$file" ] && [ ! -L "$file" ] || { echo 'Expected regular SSH configuration file' >&2; exit 1; }
[ "$(stat -c %u "$file")" = 0 ] || { echo 'SSH configuration must already be root-owned' >&2; exit 1; }
sshd -t
chmod 600 "$file"
stat -c '%a %U %G' "$file"
"""
    response = capture(client, privileged(command, mode), timeout=timeout, max_bytes=65536)
    if response.exit_code:
        raise RuntimeError(response.stderr.strip() or "SSH configuration permission policy failed")
    return {"policy": "ssh_config_permissions", "file": "/etc/ssh/sshd_config",
            "mode_owner": response.stdout.decode().strip(),
            "note": "Configuration content unchanged; SSH service was not restarted"}

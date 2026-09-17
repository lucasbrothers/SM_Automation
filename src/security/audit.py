from __future__ import annotations

from dataclasses import dataclass

from engine.ssh import SSHClient


@dataclass(frozen=True)
class SecurityAuditResult:
    """Store read-only Linux security baseline observations."""

    root_accounts: tuple[str, ...]
    sshd_settings: dict[str, str]
    sshd_config_mode: str


def _root_accounts(passwd_output: str) -> tuple[str, ...]:
    accounts = []
    for line in passwd_output.splitlines():
        fields = line.split(":")
        if len(fields) >= 3 and fields[2] == "0":
            accounts.append(fields[0])
    return tuple(sorted(set(accounts)))


def _sshd_settings(sshd_output: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for line in sshd_output.splitlines():
        fields = line.split(None, 1)
        if len(fields) == 2 and fields[0] in {
            "permitrootlogin",
            "passwordauthentication",
            "pubkeyauthentication",
        }:
            settings[fields[0]] = fields[1].strip()
    return settings


def audit_linux_server(client: SSHClient) -> SecurityAuditResult:
    """Collect a read-only Linux security baseline through an existing SSH client."""
    passwd_output = client.execute("sudo -n getent passwd")
    sshd_output = client.execute("sudo -n sshd -T")
    if len(_sshd_settings(sshd_output)) != 3:
        raise ValueError("Required SSH audit observations are missing.")
    config_mode = client.execute(
        "sudo -n stat -c '%a %U %G' /etc/ssh/sshd_config"
    ).strip()
    return SecurityAuditResult(
        root_accounts=_root_accounts(passwd_output),
        sshd_settings=_sshd_settings(sshd_output),
        sshd_config_mode=config_mode,
    )

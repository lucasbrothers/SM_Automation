from engine.remote import CommandResult
from security import permissions
import pytest


def test_policy_checks_file_and_syntax_before_chmod(monkeypatch):
    commands = []
    def capture(client, command, **kwargs):
        commands.append(command)
        return CommandResult(b"600 root root\n", "", 0)
    monkeypatch.setattr(permissions, "capture", capture)
    result = permissions.secure_ssh_config(None, "direct", 30)
    assert result["mode_owner"] == "600 root root"
    assert "! -L" in commands[0]
    assert commands[0].index("sshd -t") < commands[0].index("chmod 600")
    assert "systemctl" not in commands[0]


def test_failed_policy_reports_failure(monkeypatch):
    monkeypatch.setattr(permissions, "capture", lambda *args, **kwargs: CommandResult(b"", "Invalid configuration", 1))
    with pytest.raises(RuntimeError, match="Invalid configuration"):
        permissions.secure_ssh_config(None, "direct", 30)

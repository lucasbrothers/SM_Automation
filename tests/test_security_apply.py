import pytest

from security.apply import build_sshd_apply_command


def test_build_apply_command_contains_backup_validation_and_reload():
    command = build_sshd_apply_command("permitrootlogin", "without-password")

    assert "sshd_config" in command
    assert "sm_automation" in command
    assert "sshd -t" in command
    assert "systemctl reload sshd" in command
    assert "PermitRootLogin without-password" in command


def test_build_apply_command_rejects_unsupported_setting():
    with pytest.raises(ValueError, match="Unsupported SSH setting"):
        build_sshd_apply_command("passwordauthentication", "no")


def test_build_apply_command_rejects_unsafe_value():
    with pytest.raises(ValueError, match="unsupported characters"):
        build_sshd_apply_command("permitrootlogin", "no; touch /tmp/bad")

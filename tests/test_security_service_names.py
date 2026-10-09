from unittest.mock import Mock
import pytest
from security import apply


@pytest.mark.parametrize("reconnect_fails", [False, True])
def test_ubuntu_service_used_for_apply_and_rollback(monkeypatch, reconnect_fails):
    client = Mock(); client.hostname = "lab"; client.ip = "127.0.0.1"
    client.execute.return_value = "backup=/etc/ssh/.sm_automation.abcdefghij/sshd_config\ndigest=" + "a" * 64
    probe = Mock()
    if reconnect_fails:
        probe.execute.side_effect = RuntimeError("connection failed")
    monkeypatch.setattr(apply, "SSHClient", lambda *args, **kwargs: probe)
    actions = [{"type": "set_sshd_option", "parameter": "pubkeyauthentication", "current": "no", "recommended": "yes"}]
    if reconnect_fails:
        with pytest.raises(apply.SSHCommandError, match="original configuration restored"):
            apply.apply_sshd_settings(client, actions, service_name="ssh")
    else:
        apply.apply_sshd_settings(client, actions, service_name="ssh")
    for call in client.execute.call_args_list:
        assert "systemctl reload sshd" not in call.args[0]
        assert "systemctl reload ssh" in call.args[0]
    probe.close.assert_called_once()

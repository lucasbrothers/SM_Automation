from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from core.inventory import ServerRecord
from engine.ssh import SSHClient, SSHCommandError
from security.apply import apply_sshd_settings, build_sshd_apply_batch_command, validate_plan, _rollback_command


ACTIONS = [
    {"type": "set_sshd_option", "parameter": "permitrootlogin", "current": "yes", "recommended": "no"},
    {"type": "set_sshd_option", "parameter": "pubkeyauthentication", "current": "no", "recommended": "yes"},
]
ORIGINAL = "# original\nPermitRootLogin yes\nPubkeyAuthentication no\nPort 22\n"


def plan():
    return [{"hostname": "TEST", "ip": "192.0.2.1", "scope": "sshd_settings",
             "status": "action_required", "actions": copy.deepcopy(ACTIONS)}]


@pytest.mark.parametrize("change", [
    {"ip": "192.0.2.2"}, {"status": "blocked"}, {"scope": "all"},
    {"hostname": "OTHER"}, {"actions": []},
    {"actions": [dict(ACTIONS[0], current=None)]},
    {"actions": [dict(ACTIONS[0], type="shell")]},
    {"actions": [ACTIONS[0], ACTIONS[0]]},
    {"actions": [dict(ACTIONS[0], recommended="invalid")]},
])
def test_invalid_plan_rejected_before_execution(change):
    records = plan()
    records[0].update(change)
    with pytest.raises(ValueError):
        validate_plan(records, [ServerRecord("TEST", "192.0.2.1", "Linux")])


def test_duplicate_plan_and_wrong_platform_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        validate_plan(plan() + plan(), [ServerRecord("TEST", "192.0.2.1", "Linux")])
    with pytest.raises(ValueError, match="platform"):
        validate_plan(plan(), [ServerRecord("TEST", "192.0.2.1", "AIX")])


@pytest.fixture
def shell_runner(tmp_path):
    bash = shutil.which("bash")
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.is_file():
        bash = str(git_bash)
    if bash is None:
        pytest.skip("A POSIX shell is required for generated-command integration tests")
    config = tmp_path / "sshd_config"
    config.write_text(ORIGINAL, encoding="utf-8")
    # Substitute the fixed remote directory; no real sshd, sudo or systemctl runs.
    prelude = r'''
sshd() {
    if [ "$1" = -t ]; then
        if [ "${FAIL_VALIDATE:-0}" = 1 ] && [ "$3" != "$cfg" ]; then echo "injected validation failure" >&2; return 1; fi
        return 0
    fi
    awk 'tolower($1) == "permitrootlogin" || tolower($1) == "pubkeyauthentication" {print tolower($1), $2}' "$cfg"
    if [ "${FAIL_EFFECTIVE:-0}" = 1 ] && grep -q '^PermitRootLogin no' "$cfg"; then
        echo 'permitrootlogin yes'
    fi
    if [ -f "$cfg.post_reload_failure" ]; then echo 'pubkeyauthentication no'; fi
}
systemctl() {
    if [ "${FAIL_RELOAD:-0}" = 1 ] && [ ! -f "$cfg.reloaded" ]; then
        touch "$cfg.reloaded"
        echo "injected reload failure" >&2
        return 1
    fi
    if [ "${FAIL_POST_RELOAD:-0}" = 1 ] && [ ! -f "$cfg.reloaded" ]; then
        touch "$cfg.reloaded" "$cfg.post_reload_failure"
    else
        rm -f "$cfg.post_reload_failure"
    fi
    return 0
}
'''
    def run(actions=None, mode="", config_text=None, command=None):
        if config_text is not None:
            config.write_text(config_text, encoding="utf-8")
        command = command or build_sshd_apply_batch_command(ACTIONS if actions is None else actions)
        script = shlex.split(command)[-1].replace("/etc/ssh", tmp_path.as_posix())
        assert "/etc/ssh" not in script
        result = subprocess.run([bash, "-c", mode + "\n" + prelude + script],
                                capture_output=True, text=True, timeout=15)
        return result, config, list(tmp_path.glob(".sm_automation.*/sshd_config"))
    return run


def test_batch_applies_both_settings_and_saves_one_original(shell_runner):
    result, config, backups = shell_runner()
    assert result.returncode == 0, result.stderr
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == ORIGINAL
    actual = config.read_text(encoding="utf-8")
    assert "PermitRootLogin no\n" in actual
    assert "PubkeyAuthentication yes\n" in actual
    assert "Port 22\n" in actual
    assert f"digest={hashlib.sha256(config.read_bytes()).hexdigest()}" in result.stdout


@pytest.mark.parametrize("directive", ["Include conf.d/*.conf", "Match User example", "  mAtCh all", "Include=conf.d/*.conf"])
def test_conditional_configuration_is_unchanged(shell_runner, directive):
    original = ORIGINAL + directive + "\n"
    result, config, backups = shell_runner(config_text=original)
    assert result.returncode != 0
    assert "Include/Match" in result.stderr
    assert config.read_text(encoding="utf-8") == original
    assert not backups


@pytest.mark.parametrize("mode", ["FAIL_VALIDATE=1", "FAIL_RELOAD=1", "FAIL_EFFECTIVE=1", "FAIL_POST_RELOAD=1"])
def test_failure_restores_entire_original(shell_runner, mode):
    result, config, backups = shell_runner(mode=mode)
    assert result.returncode != 0
    assert config.read_text(encoding="utf-8") == ORIGINAL
    if mode == "FAIL_VALIDATE=1":
        assert "injected validation failure" in result.stderr
    elif mode == "FAIL_RELOAD=1":
        assert "injected reload failure" in result.stderr
    else:
        assert "recommended mismatch" in result.stderr
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == ORIGINAL
    assert not (config.parent / ".sm_automation.lock").exists()


def test_stale_plan_aborts_before_backup(shell_runner):
    actions = copy.deepcopy(ACTIONS)
    actions[0]["current"] = "no"
    result, config, backups = shell_runner(actions)
    assert result.returncode != 0
    assert "current mismatch" in result.stderr
    assert config.read_text(encoding="utf-8") == ORIGINAL
    assert not backups


def test_repeated_apply_preserves_previous_backup(shell_runner):
    first, _, backups = shell_runner()
    assert first.returncode == 0
    original_backup = backups[0]
    reverse = [{**action, "current": action["recommended"], "recommended": action["current"]} for action in ACTIONS]
    second, config, backups = shell_runner(reverse)
    assert second.returncode == 0, second.stderr
    assert len(backups) == 2
    assert original_backup.read_text(encoding="utf-8") == ORIGINAL


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_reconnect_failure_attempts_rollback_on_original_session(monkeypatch, rollback_fails):
    calls = []
    client = SSHClient("TEST", "192.0.2.1")
    def execute(command):
        calls.append(command)
        if len(calls) == 1:
            return "backup=/etc/ssh/.sm_automation.abcdefghij/sshd_config\ndigest=" + "a" * 64 + "\n"
        if rollback_fails:
            raise SSHCommandError("rollback unavailable")
        return ""
    client.execute = execute
    class FailedProbe:
        closed = False
        def __init__(self, *args, **kwargs):
            pass
        def execute(self, command):
            raise OSError("reconnect refused")
        def close(self):
            self.closed = True
    monkeypatch.setattr("security.apply.SSHClient", FailedProbe)
    with pytest.raises(SSHCommandError, match="ROLLBACK FAILED" if rollback_fails else "original configuration restored"):
        apply_sshd_settings(client, ACTIONS)
    assert len(calls) == 2
    assert "manual recovery required" in calls[1]


@pytest.mark.parametrize("concurrent_change", [False, True])
def test_reconnect_rollback_script_checks_digest(shell_runner, concurrent_change):
    first, config, backups = shell_runner()
    assert first.returncode == 0
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    backup = "/etc/ssh/" + backups[0].parent.name + "/sshd_config"
    changed = None
    if concurrent_change:
        changed = config.read_text(encoding="utf-8") + "# concurrent edit\n"
    result, config, _ = shell_runner(command=_rollback_command(backup, digest), config_text=changed)
    if concurrent_change:
        assert result.returncode != 0
        assert "manual recovery" in result.stderr
        assert config.read_text(encoding="utf-8") == changed
    else:
        assert result.returncode == 0, result.stderr
        assert config.read_text(encoding="utf-8") == ORIGINAL

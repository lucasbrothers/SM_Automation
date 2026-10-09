import subprocess
import sys
import io
import tarfile

import pytest

from backup.profiles import account_commands, command_group, commands, unix_archive


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
def test_configuration_archive_preserves_dangling_symlink(tmp_path):
    link = tmp_path / "configuration-link"
    link.symlink_to("missing-target")
    absent = tmp_path / "absent"
    result = subprocess.run(["sh", "-c", unix_archive([str(link), str(absent)])], capture_output=True)
    assert result.returncode == 0
    assert result.stderr.decode() == f"Missing optional path: {absent}\n"
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        member = archive.getmember(str(link).lstrip("/"))
        assert member.issym() and member.linkname == "missing-target"


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("tool", ["chage", "sudo"])
def test_account_diagnostic_retains_earlier_failure_with_account_name(tool):
    stub = "getent() { printf 'first:x:1000:1000::/:/bin/sh\\nsecond:x:1001:1001::/:/bin/sh\\n'; }; "
    stub += tool + "() { for arg do [ \"$arg\" != first ] || return 9; done; echo success; }; "
    result = subprocess.run(["sh", "-c", stub + account_commands(tool)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "===== second =====" in result.stdout and "success" in result.stdout
    assert result.stderr == "Account diagnostic failed: first / exit_code=9\n"


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("scenario", ["missing", "failed", "success"])
def test_firewall_backup_distinguishes_missing_tools_and_failed_collection(scenario):
    availability = "return 1" if scenario == "missing" else '[ "$2" = "nft" ]'
    stub = 'command() { ' + availability + '; }; nft() { echo rules; return ' + ("7" if scenario == "failed" else "0") + '; }; '
    result = subprocess.run(["sh", "-c", stub + commands("linux")["firewall"]], capture_output=True, text=True)
    assert result.returncode == (0 if scenario == "success" else 1)
    assert "Missing optional tool: iptables-save" in result.stderr
    assert ("No firewall rule collection tool available" in result.stderr) == (scenario == "missing")
    assert ("rules" in result.stdout) == (scenario != "missing")
    assert ("Command failed: nft / exit_code=7" in result.stderr) == (scenario == "failed")


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("failure_position", [0, 1, 2, None])
def test_command_group_retains_all_output_and_any_failure(failure_position):
    steps = [f"printf 'step{index}\\n'; exit {7 if index == failure_position else 0}" for index in range(3)]
    result = subprocess.run(["sh", "-c", command_group(*steps)], capture_output=True, text=True)
    assert result.stdout == "step0\nstep1\nstep2\n"
    assert result.returncode == (0 if failure_position is None else 1)
    if failure_position is None:
        assert result.stderr == ""
    else:
        assert f"step{failure_position}" in result.stderr and "exit_code=7" in result.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("inventory", ["return 1", "return 0", "printf 'lab\\n'"])
def test_cron_backup_requires_inventory_but_accepts_absent_crontab(inventory):
    stub = "cut() { " + inventory + "; }; crontab() { echo 'no crontab for lab'; return 1; }; "
    result = subprocess.run(["sh", "-c", stub + commands("linux")["schedule"]], capture_output=True, text=True)
    assert result.returncode == (0 if inventory.startswith("printf") else 1)
    if inventory.startswith("printf"):
        assert "===== lab =====" in result.stdout and "no crontab for lab" in result.stdout

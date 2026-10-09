import subprocess
import sys

import pytest

from backup.profiles import command_group, commands


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("failure_position", [0, 1, 2, None])
def test_command_group_retains_all_output_and_any_failure(failure_position):
    steps = [f"printf 'step{index}\\n'; exit {7 if index == failure_position else 0}" for index in range(3)]
    result = subprocess.run(["sh", "-c", command_group(*steps)], capture_output=True, text=True)
    assert result.stdout == "step0\nstep1\nstep2\n"
    assert result.returncode == (0 if failure_position is None else 1)


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("inventory", ["return 1", "return 0", "printf 'lab\\n'"])
def test_cron_backup_requires_inventory_but_accepts_absent_crontab(inventory):
    stub = "cut() { " + inventory + "; }; crontab() { echo 'no crontab for lab'; return 1; }; "
    result = subprocess.run(["sh", "-c", stub + commands("linux")["schedule"]], capture_output=True, text=True)
    assert result.returncode == (0 if inventory.startswith("printf") else 1)
    if inventory.startswith("printf"):
        assert "===== lab =====" in result.stdout and "no crontab for lab" in result.stdout

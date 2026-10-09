import subprocess
import sys

import pytest

from backup.profiles import command_group


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX shell check runs in WSL")
@pytest.mark.parametrize("failure_position", [0, 1, 2, None])
def test_command_group_retains_all_output_and_any_failure(failure_position):
    steps = [f"printf 'step{index}\\n'; exit {7 if index == failure_position else 0}" for index in range(3)]
    result = subprocess.run(["sh", "-c", command_group(*steps)], capture_output=True, text=True)
    assert result.stdout == "step0\nstep1\nstep2\n"
    assert result.returncode == (0 if failure_position is None else 1)

import subprocess
import sys
from unittest.mock import Mock

import pytest
from patch.manager import MANAGER_COMMAND, make_plan


@pytest.mark.skipif(sys.platform != "linux", reason="Shell discovery is checked in WSL")
@pytest.mark.parametrize("distribution,tools,expected", [
    ("debian", "apt-get dpkg-query dnf rpm", "apt"),
    ("redhat", "apt-get dpkg-query dnf rpm", "dnf"),
    ("redhat", "apt-get dpkg-query dnf", "unsupported"),
    ("debian", "dnf rpm", "unsupported"),
])
def test_native_distribution_does_not_fall_back_to_foreign_package_manager(distribution, tools, expected):
    stub = 'test() { case "$2" in /etc/' + distribution + '* ) return 0;; *) return 1;; esac; }; '
    stub += 'command() { case " ' + tools + ' " in *" $2 "*) return 0;; *) return 1;; esac; }; '
    result = subprocess.run(["sh", "-c", stub + MANAGER_COMMAND], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == expected


def test_unsupported_manager_stops_before_building_a_patch_plan():
    client = Mock(); client.execute.return_value = "unsupported"
    with pytest.raises(ValueError, match="native package manager"):
        make_plan(client, ["example"], "direct")
    client.execute.assert_called_once_with(MANAGER_COMMAND)

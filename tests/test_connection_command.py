import subprocess
import sys
from types import SimpleNamespace

import pytest

from monitoring import connections


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX command check runs in WSL")
@pytest.mark.parametrize("failed_family", ["inet", "inet6", None])
def test_aix_collection_preserves_either_command_failure(monkeypatch, failed_family):
    calls = []

    def capture(client, command, **options):
        stub = 'netstat() { printf "%s\\n" "$3"; [ "$3" != "' + str(failed_family) + '" ]; }; '
        result = subprocess.run(["sh", "-c", stub + command], capture_output=True)
        calls.append(result.stdout.decode())
        return SimpleNamespace(exit_code=result.returncode, stdout=result.stdout, stderr="")

    monkeypatch.setattr(connections, "capture", capture)
    if failed_family:
        with pytest.raises(RuntimeError, match="netstat failed"):
            connections.collect_connections(None, "aix", 10)
    else:
        assert connections.collect_connections(None, "aix", 10)["connections"] == []
    assert calls == ["inet\ninet6\n"]

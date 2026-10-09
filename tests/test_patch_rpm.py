from types import SimpleNamespace
import pytest
from patch import rpm


def test_updates_match_installed_architectures_and_exclude_obsoletes():
    installed = "kernel\t0:1.0-1\tx86_64\nkernel\t0:1.0-2\tx86_64\nlib\t1:1.0-1\ti686\n"
    output = "kernel.x86_64 1.1-1 repo\nlib.i686 1:1.1-1 repo\nlib.x86_64 1:1.1-1 repo\nObsoleting Packages\nreplacement.noarch 1.0 repo\n"
    packages = rpm.parse_updates(output, installed)
    assert [p["name"] for p in packages] == ["kernel", "lib"]
    assert packages[0]["installed"] == "1.0-1, 1.0-2"
    assert packages[1]["installed"] == "1:1.0-1"


@pytest.mark.parametrize("code", [0, 100, 1])
def test_dnf_exit_status_and_cache_only_boundary(monkeypatch, code):
    commands = []
    def capture(client, command, **kwargs):
        commands.append(command)
        if len(commands) == 1:
            return SimpleNamespace(exit_code=0, stdout=b"pkg\t0:1.0-1\tnoarch\n", stderr="")
        return SimpleNamespace(exit_code=code, stdout=b"pkg.noarch 1.1-1 repo\n" if code == 100 else b"", stderr="cache unavailable" if code == 1 else "")
    monkeypatch.setattr(rpm, "capture", capture)
    if code == 1:
        with pytest.raises(RuntimeError, match="cache unavailable"):
            rpm.list_updates(None, "direct")
    else:
        result = rpm.list_updates(None, "direct")
        assert len(result["packages"]) == (1 if code == 100 else 0)
    assert "--cacheonly check-update" in commands[1]

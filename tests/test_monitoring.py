import pytest

from monitoring.collector import _parse_filesystem, _parse_load, _parse_memory


def test_parse_load_average():
    assert _parse_load("0.10 0.20 0.30 1/100 12345\n") == (0.1, 0.2, 0.3)


def test_parse_memory():
    output = """              total        used        free      shared  buff/cache   available
Mem:           4096        1024        2048          10        1024        3000
"""
    assert _parse_memory(output) == {
        "total": 4096,
        "used": 1024,
        "free": 2048,
        "shared": 10,
        "cache": 1024,
        "available": 3000,
    }


def test_parse_filesystem():
    output = "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda1 100000 40000 60000 40% /\n"
    assert _parse_filesystem(output)["capacity"] == "40%"
    assert _parse_filesystem(output)["mounted_on"] == "/"


def test_parse_load_rejects_invalid_output():
    with pytest.raises(ValueError, match="/proc/loadavg"):
        _parse_load("not-a-load")

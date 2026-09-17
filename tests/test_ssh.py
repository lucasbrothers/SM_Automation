from __future__ import annotations

import pytest

from core.inventory import ServerRecord
from engine.ssh import (
    SSHClient,
    SSHCommandError,
    distribute_public_key_to_inventory,
    run_inventory_commands,
)


class FakeStream:
    def __init__(self, data: str, *, return_code: int):
        self._data = data
        self.channel = type("Channel", (), {"recv_exit_status": lambda self: return_code})()

    def read(self):
        return self._data.encode("utf-8")

    def close(self):
        pass


def test_ssh_client_uses_paramiko_for_remote_command(monkeypatch):
    class FakeSSH:
        def load_system_host_keys(self):
            self.loaded = True

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, hostname, username, key_filename=None, password=None, timeout=None, port=22):
            assert hostname == "10.10.10.1"
            assert username == "D25950"
            assert timeout == 15
            assert port == 22

        def exec_command(self, command, timeout=None):
            assert command == "uname -a"
            return (None, FakeStream("ok\n", return_code=0), FakeStream("", return_code=0))

        def close(self):
            pass

    fake_client = FakeSSH()
    monkeypatch.setattr("engine.ssh.paramiko.SSHClient", lambda: fake_client)

    client = SSHClient("WEB01", "10.10.10.1", user="D25950", timeout=15)
    result = client.execute("uname -a")

    assert result == "ok\n"
    assert fake_client.loaded
    assert isinstance(fake_client.policy, __import__("paramiko").RejectPolicy)


def test_ssh_client_raises_on_failed_command(monkeypatch):
    class FakeSSH:
        def load_system_host_keys(self):
            self.loaded = True

        def set_missing_host_key_policy(self, policy):
            pass

        def connect(self, *args, **kwargs):
            pass

        def exec_command(self, command, timeout=None):
            return (None, FakeStream("", return_code=1), FakeStream("Permission denied", return_code=1))

        def close(self):
            pass

    fake_client = FakeSSH()
    monkeypatch.setattr("engine.ssh.paramiko.SSHClient", lambda: fake_client)

    client = SSHClient("WEB02", "10.10.10.2")

    with pytest.raises(SSHCommandError, match="Permission denied"):
        client.execute("whoami")


def test_run_inventory_commands_executes_for_each_server(monkeypatch):
    servers = [
        ServerRecord(hostname="WEB01", ip="10.10.10.1", os="Linux"),
        ServerRecord(hostname="DB01", ip="10.10.10.2", os="AIX"),
    ]

    outputs = {
        "WEB01": "uptime\n",
        "DB01": "svcs\n",
    }

    monkeypatch.setattr("engine.ssh.Inventory.load", lambda self, path: servers)

    def fake_execute(self, command):
        return outputs[self.hostname]

    monkeypatch.setattr("engine.ssh.SSHClient.execute", fake_execute)

    result = run_inventory_commands("servers.txt", "uname -a", timeout=20)

    assert result == outputs


def test_distribute_public_key_uses_password_and_idempotent_command(monkeypatch):
    servers = [ServerRecord(hostname="WEB01", ip="10.10.10.1", os="Linux")]
    captured = {}

    monkeypatch.setattr("engine.ssh.Inventory.load", lambda self, path: servers)

    def fake_execute(self, command):
        captured["password"] = self.password
        captured["command"] = command
        return "installed\n"

    monkeypatch.setattr("engine.ssh.SSHClient.execute", fake_execute)

    result = distribute_public_key_to_inventory(
        "servers.txt",
        "ssh-rsa AAAA key@example",
        password="Abllife1!",
    )

    assert result == {"WEB01": "installed\n"}
    assert captured["password"] == "Abllife1!"
    assert "ssh-rsa AAAA key@example" in captured["command"]
    assert "grep -qxF" in captured["command"]
    assert "Abllife1!" not in captured["command"]


def test_distribute_public_key_rejects_multiline_key():
    with pytest.raises(ValueError, match="single nonempty line"):
        distribute_public_key_to_inventory(
            "servers.txt",
            "ssh-rsa AAAA\nmalicious-command",
            password="Abllife1!",
        )


def test_exec_failure_preserves_original_error():
    class BrokenTransport:
        def exec_command(self, *args, **kwargs):
            raise OSError("transport failed")
    client = SSHClient("TEST", "192.0.2.1")
    client._client = BrokenTransport()
    with pytest.raises(SSHCommandError, match="transport failed") as error:
        client.execute("true")
    assert isinstance(error.value.__cause__, OSError)


def test_connection_failure_closes_transport(monkeypatch):
    class BrokenClient:
        closed = False
        def load_system_host_keys(self):
            pass
        def set_missing_host_key_policy(self, policy):
            assert isinstance(policy, __import__("paramiko").RejectPolicy)
        def connect(self, **kwargs):
            raise OSError("untrusted or unavailable")
        def close(self):
            self.closed = True
    transport = BrokenClient()
    monkeypatch.setattr("engine.ssh.paramiko.SSHClient", lambda: transport)
    with pytest.raises(OSError):
        SSHClient("TEST", "192.0.2.1").connect()
    assert transport.closed

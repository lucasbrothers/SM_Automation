from __future__ import annotations

from pathlib import Path
import shlex

import paramiko

from core.inventory import Inventory


class SSHCommandError(RuntimeError):
    """Raised when an SSH command fails to execute."""


def _authorized_keys_command(public_key: str) -> str:
    """Build an idempotent command for installing one public key."""
    key = public_key.strip()
    if not key or any(char in key for char in "\r\n"):
        raise ValueError("public_key must be a single nonempty line.")

    quoted_key = shlex.quote(key)
    return (
        "umask 077; mkdir -p ~/.ssh; "
        "touch ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
        f"grep -qxF -- {quoted_key} ~/.ssh/authorized_keys || "
        f"printf '%s\\n' {quoted_key} >> ~/.ssh/authorized_keys"
    )


class SSHClient:
    """Execute remote commands over SSH for a single server entry."""

    def __init__(
        self,
        hostname: str,
        ip: str,
        user: str = "D25950",
        timeout: int = 30,
        *,
        password: str | None = None,
        key_filename: str | Path | None = None,
        port: int = 22,
    ):
        self.hostname = hostname
        self.ip = ip
        self.user = user
        self.timeout = timeout
        self.password = password
        self.key_filename = str(key_filename) if key_filename is not None else None
        self.port = port
        self._client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        """Open an SSH connection to the target host."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict[str, object] = {
            "hostname": self.ip,
            "username": self.user,
            "timeout": self.timeout,
            "port": self.port,
        }
        if self.key_filename is not None:
            kwargs["key_filename"] = self.key_filename
        if self.password is not None:
            kwargs["password"] = self.password

        client.connect(**kwargs)
        self._client = client

    def execute(self, command: str) -> str:
        """Execute a command on the remote host and return stdout."""
        if not command or not command.strip():
            raise SSHCommandError("Command is empty.")

        if self._client is None:
            self.connect()

        client = self._client
        if client is None:
            raise SSHCommandError("SSH connection is not initialized.")

        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=self.timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
            exit_status = stdout.channel.recv_exit_status()
        except (paramiko.SSHException, OSError, ValueError) as exc:
            raise SSHCommandError(
                f"SSH command failed for {self.hostname} ({self.ip}): {exc}"
            ) from exc
        finally:
            if stdin is not None:
                stdin.close()
            if stdout is not None:
                stdout.close()
            if stderr is not None:
                stderr.close()

        if exit_status != 0:
            raise SSHCommandError(
                f"SSH command failed for {self.hostname} ({self.ip}): {error.strip() or output.strip() or 'unknown error'}"
            )

        return output

    def close(self) -> None:
        """Close the SSH connection."""
        if self._client is not None:
            self._client.close()
            self._client = None


def run_inventory_commands(
    server_file: str | Path,
    command: str,
    *,
    user: str = "D25950",
    timeout: int = 30,
) -> dict[str, str]:
    """Run one command across all servers listed in the inventory file."""
    inventory = Inventory()
    servers = inventory.load(server_file)

    result: dict[str, str] = {}
    for server in servers:
        client = SSHClient(server.hostname, server.ip, user=user, timeout=timeout)
        try:
            result[server.hostname] = client.execute(command)
        finally:
            client.close()

    return result


class SSHKeyDistributor:
    """Install a public key for one inventory server account."""

    def __init__(
        self,
        hostname: str,
        ip: str,
        *,
        user: str = "D25950",
        password: str,
        timeout: int = 30,
        port: int = 22,
    ):
        self.hostname = hostname
        self.ip = ip
        self.user = user
        self.password = password
        self.timeout = timeout
        self.port = port

    def distribute(self, public_key: str) -> str:
        """Install the key and return the remote command output."""
        client = SSHClient(
            self.hostname,
            self.ip,
            user=self.user,
            password=self.password,
            timeout=self.timeout,
            port=self.port,
        )
        try:
            return client.execute(_authorized_keys_command(public_key))
        finally:
            client.close()


def distribute_public_key_to_inventory(
    server_file: str | Path,
    public_key: str,
    *,
    password: str,
    user: str = "D25950",
    timeout: int = 30,
    port: int = 22,
) -> dict[str, str]:
    """Install a public key for every server in the inventory."""
    _authorized_keys_command(public_key)
    servers = Inventory().load(server_file)
    results: dict[str, str] = {}
    for server in servers:
        distributor = SSHKeyDistributor(
            server.hostname,
            server.ip,
            user=user,
            password=password,
            timeout=timeout,
            port=port,
        )
        results[server.hostname] = distributor.distribute(public_key)
    return results

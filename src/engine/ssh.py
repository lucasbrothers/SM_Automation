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
        self.key_only = False
        self.accept_new_host_key = False
        self.host_key_registered = False
        self.host_key_fingerprint = ""

    def connect(self) -> None:
        """Open an SSH connection to the target host."""
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.accept_new_host_key:
            from engine.hostkeys import AcceptNewHostKey
            client.set_missing_host_key_policy(AcceptNewHostKey(Path.home()/".ssh"/"known_hosts",self))
        else:client.set_missing_host_key_policy(paramiko.RejectPolicy())

        kwargs: dict[str, object] = {
            "hostname": self.ip,
            "username": self.user,
            "timeout": self.timeout,
            "port": self.port,
        }
        if self.key_filename is not None:
            kwargs["key_filename"] = self.key_filename
        if self.password is not None:kwargs["password"] = self.password
        if self.password is not None or self.key_only:
            kwargs["look_for_keys"] = False
            kwargs["allow_agent"] = False

        try:
            client.connect(**kwargs)
        except Exception:
            client.close()
            raise
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

        stdin = stdout = stderr = None
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

    def execute_result(self, command, limit=1024 * 1024, input_data=None, password_prompt=False):
        """Drain both streams with a deadline and a combined output bound."""
        import time
        if self._client is None:
            self.connect()
        channel = self._client.get_transport().open_session(timeout=self.timeout)
        output = bytearray(); errors = bytearray(); deadline = time.monotonic() + self.timeout
        try:
            if password_prompt:
                channel.get_pty()
            channel.exec_command(command)
            sent = False
            if not password_prompt:
                if input_data is not None:
                    channel.sendall(input_data)
                channel.shutdown_write()
            while True:
                if time.monotonic() >= deadline:
                    raise SSHCommandError("Command timed out; remote command may still be running")
                for ready, receive, buffer in ((channel.recv_ready, channel.recv, output),
                                                (channel.recv_stderr_ready, channel.recv_stderr, errors)):
                    if ready():
                        buffer.extend(receive(32768))
                if password_prompt and not sent and b"Password:" in output + errors:
                    if input_data is None:
                        raise SSHCommandError("Root password is required for su")
                    channel.sendall(input_data); sent = True
                if len(output) + len(errors) > limit:
                    raise SSHCommandError("Command output exceeds 1 MiB; remote command may still be running")
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                time.sleep(0.01)
            return {"stdout": output.decode("utf-8", errors="replace"),
                    "stderr": errors.decode("utf-8", errors="replace"), "exit_code": channel.recv_exit_status()}
        finally:
            channel.close()

    def execute_root(self, command, login_password="", root_password=""):
        import uuid
        marker = "__SM_ROOT_" + uuid.uuid4().hex + "__"
        wrapped = '[ "$(id -u)" = 0 ] || exit 126; printf "%s\\n" ' + shlex.quote(marker) + '; exec sh -c ' + shlex.quote(command) + ' < /dev/null'
        if self.user == "root":
            return self.execute_result(command)
        result = self.execute_result("sudo -S -p '' sh -c " + shlex.quote(wrapped),
                                     input_data=(login_password + "\n").encode())
        if marker in result["stdout"]:
            result["stdout"] = result["stdout"].split(marker, 1)[1].lstrip("\r\n")
            return result
        # No root marker means the user's command never started: safe to try su.
        if not root_password:
            return {"stdout": "", "stderr": "sudo root transition failed. Enter the root password to try su. " + result["stderr"], "exit_code": result["exit_code"] or 126}
        result = self.execute_result("stty -echo; LC_ALL=C su - root -c " + shlex.quote(wrapped),
                                     input_data=(root_password + "\n").encode(), password_prompt=True)
        if marker in result["stdout"]:
            result["stdout"] = result["stdout"].split(marker, 1)[1].lstrip("\r\n")
        else:
            result["stderr"] = "su root transition failed. " + result["stderr"]
            result["exit_code"] = result["exit_code"] or 126
        return result

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
        password: str | None = None,
        key_filename: str | Path | None = None,
        timeout: int = 30,
        port: int = 22,
    ):
        if password is None and key_filename is None:
            raise ValueError("password or key_filename is required.")
        self.hostname = hostname
        self.ip = ip
        self.user = user
        self.password = password
        self.key_filename = key_filename
        self.timeout = timeout
        self.port = port

    def distribute(self, public_key: str) -> str:
        """Install the key and return the remote command output."""
        client = SSHClient(
            self.hostname,
            self.ip,
            user=self.user,
            password=self.password,
            key_filename=self.key_filename,
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
    password: str | None = None,
    key_filename: str | Path | None = None,
    user: str = "D25950",
    timeout: int = 30,
    port: int = 22,
) -> dict[str, str]:
    """Install a public key for every server in the inventory."""
    if password is None and key_filename is None:
        raise ValueError("password or key_filename is required.")
    _authorized_keys_command(public_key)
    servers = Inventory().load(server_file)
    results: dict[str, str] = {}
    for server in servers:
        distributor = SSHKeyDistributor(
            server.hostname,
            server.ip,
            user=user,
            password=password,
            key_filename=key_filename,
            timeout=timeout,
            port=port,
        )
        results[server.hostname] = distributor.distribute(public_key)
    return results

"""Bounded binary SSH capture for server-side jobs."""
from __future__ import annotations

import base64
import shlex
import time
from dataclasses import dataclass

from engine.ssh import SSHClient, SSHCommandError


@dataclass
class CommandResult:
    stdout: bytes
    stderr: str
    exit_code: int


def powershell(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return "powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand " + encoded


def privileged(command: str, mode: str) -> str:
    if mode == "sudo":
        return "sudo -n sh -c " + shlex.quote(command)
    if mode == "sudo-su":
        return "sudo -n su - root -c " + shlex.quote(command)
    if mode == "su":
        return "su - root -c " + shlex.quote(command)
    return "sh -c " + shlex.quote(command)


def capture(client: SSHClient, command: str, *, timeout: int = 180,
            max_bytes: int = 64 * 1024 * 1024) -> CommandResult:
    """Drain stdout/stderr together without a PTY or a plaintext temp file."""
    if client._client is None:
        client.connect()
    transport = client._client.get_transport()
    if transport is None:
        raise SSHCommandError("SSH transport is unavailable")
    channel = transport.open_session(timeout=client.timeout)
    output, errors = bytearray(), bytearray()
    deadline = time.monotonic() + timeout
    try:
        channel.settimeout(client.timeout)
        channel.exec_command(command)
        channel.shutdown_write()
        while True:
            if time.monotonic() > deadline:
                raise SSHCommandError("Command timed out; remote completion is unknown")
            if channel.recv_ready():
                output.extend(channel.recv(65536))
            if channel.recv_stderr_ready():
                errors.extend(channel.recv_stderr(65536))
            if len(output) + len(errors) > max_bytes:
                raise SSHCommandError("Capture limit exceeded; artifact was not saved")
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(0.01)
        return CommandResult(bytes(output), errors.decode("utf-8", errors="replace"), channel.recv_exit_status())
    finally:
        channel.close()

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
            max_bytes: int = 64 * 1024 * 1024, input_data=None) -> CommandResult:
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
        if input_data is not None:channel.sendall(input_data)
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


def capture_root(client, command, *, login_password="", root_password="", timeout=180, max_bytes=64*1024*1024):
    """Authenticate sudo/su over stdin, verify UID 0, and preserve binary stdout."""
    import secrets
    marker="__SM_BACKUP_ROOT_"+secrets.token_hex(16)+"__"
    wrapped='[ "$(id -u)" = 0 ] || exit 126; cd / || exit 126; printf "%s\\n" '+shlex.quote(marker)+' >&2; exec sh -c '+shlex.quote(command)+' < /dev/null'
    if client.user=="root":
        attempts=[("sh -c "+shlex.quote(wrapped),None)]
    else:
        attempts=[("sudo -S -p '' sh -c "+shlex.quote(wrapped),(login_password+"\n").encode())]
        if root_password:attempts.append(("LC_ALL=C su - root -c "+shlex.quote(wrapped),(root_password+"\n").encode()))
    for invocation,secret in attempts:
        result=capture(client,invocation,timeout=timeout,max_bytes=max_bytes,input_data=secret)
        if marker in result.stderr:
            prefix,rest=result.stderr.split(marker,1)
            import re
            prefix=re.sub(r"[Pp]assword:\s*$","",prefix)
            result.stderr=prefix+rest.lstrip("\r\n")
            return result
    raise SSHCommandError("Backup root transition failed. Configure sudo permission/login password or supply a root password; no unprivileged backup was accepted")


def powershell_diagnostics(text):
    """Remove only well-formed CLIXML documents containing progress records alone.
    Plain stderr, malformed XML, and mixed/error/warning documents remain intact.
    The collector keeps the original stream in encrypted metadata for auditing.
    """
    import re
    import xml.etree.ElementTree as ET
    pieces=re.split(r"(?m)^#< CLIXML\r?\n",text)
    if len(pieces)==1:return text
    output=pieces[0]
    for piece in pieces[1:]:
        end=piece.find('</Objs>')
        document=piece[:end+7] if end>=0 else ''
        safe=False
        if document and '<!DOCTYPE' not in document and '<!ENTITY' not in document:
            try:
                root=ET.fromstring(document)
                safe=root.tag.rsplit('}',1)[-1]=='Objs' and len(root)>0 and all(child.attrib.get('S')=='progress' for child in root)
            except ET.ParseError:pass
        output+=piece[end+7:] if safe else '#< CLIXML\n'+piece
    return output

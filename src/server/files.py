"""Transfers run between a managed SSH client and the Linux main server."""
import os
import stat
import re
from pathlib import Path

LIMIT = 8 * 1024 * 1024

def validate(params):
    direction = params.get("direction")
    main = params.get("server_path"); remote = params.get("client_path")
    if direction not in {"upload", "download"}:
        raise ValueError("Choose upload (CLIENT to SERVER) or download (SERVER to CLIENT)")
    if not isinstance(main, str) or not main.startswith("/") or "\x00" in main:
        raise ValueError("SERVER path must be an absolute Linux path")
    if not isinstance(remote, str) or not (remote.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", remote)) or "\x00" in remote:
        raise ValueError("CLIENT path must be absolute")
    return {"direction": direction, "server_path": main, "client_path": remote}

def transfer(client, params):
    params = validate(params); path = Path(params["server_path"])
    if client._client is None:
        client.connect()
    with client._client.open_sftp() as sftp:
        sftp.get_channel().settimeout(client.timeout)
        remote = params["client_path"]
        if params["direction"] == "upload":
            info = sftp.lstat(remote)
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                raise ValueError("CLIENT source must be a regular file up to 8 MiB")
            with sftp.open(remote, "rb") as source:
                content = source.read(LIMIT + 1)
            if len(content) > LIMIT:
                raise ValueError("Transfer limit is 8 MiB")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as target:
                    target.write(content); target.flush(); os.fsync(target.fileno())
            except Exception:
                path.unlink(missing_ok=True); raise
        else:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                    raise ValueError("SERVER source must be a regular file up to 8 MiB")
                content = source.read(LIMIT + 1)
            if len(content) > LIMIT:
                raise ValueError("Transfer limit is 8 MiB")
            with sftp.open(remote, "wx") as target:
                target.write(content); target.flush()
        return {**params, "bytes": len(content), "status": "completed"}


CHUNK = 1024 * 1024


def gui_transfer(method, params):
    import base64
    import fcntl
    path = params.get("path")
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise ValueError("Enter an absolute Linux SERVER path")
    path = Path(path)
    if method == "file.list":
        entries = []
        for entry in path.iterdir():
            info = entry.lstat()
            entries.append({"name": entry.name, "directory": stat.S_ISDIR(info.st_mode),
                            "regular": stat.S_ISREG(info.st_mode), "size": info.st_size})
        return {"path": str(path.resolve()), "entries": sorted(entries, key=lambda e: (not e["directory"], e["name"].lower()))}
    if method in {"file.commit", "file.abort"}:
        if not re.fullmatch(r"\.sm-upload-[a-f0-9]{32}", path.name):
            raise ValueError("Invalid pending upload path")
        if method == "file.abort":
            path.unlink(missing_ok=True)
            return {"status": "aborted"}
        target = params.get("target")
        if not isinstance(target, str) or "\x00" in target or not target.startswith("/"):
            raise ValueError("Invalid target path")
        target = Path(target)
        if target.parent.resolve() != path.parent.resolve():
            raise ValueError("Upload must finish in its original directory")
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("Pending upload must be a regular file")
        if type(params.get("size")) is not int or path.stat().st_size != params["size"]:
            raise ValueError("Upload is incomplete")
        os.link(path, target, follow_symlinks=False)  # Atomic publish, never replace existing files.
        path.unlink()
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return {"path": str(target), "status": "completed"}
    offset = params.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid transfer offset")
    if method == "file.download":
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode): raise ValueError("Select a regular file")
            stream.seek(offset)
            content = stream.read(CHUNK)
        return {"content": base64.b64encode(content).decode(), "bytes": len(content), "size": info.st_size}
    if method != "file.upload": raise ValueError("Unknown file operation")
    encoded = params.get("content")
    if not isinstance(encoded, str) or len(encoded) > ((CHUNK + 2)//3)*4: raise ValueError("Invalid transfer chunk")
    content = base64.b64decode(encoded, validate=True)
    if len(content) > CHUNK: raise ValueError("Invalid transfer chunk")
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if offset == 0: flags |= os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != offset: raise ValueError("Destination changed during upload")
        stream.seek(offset); stream.write(content); stream.flush()
        if params.get("final"): os.fsync(stream.fileno())
    return {"path": str(path), "bytes": len(content)}

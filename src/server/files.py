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


def gui_transfer(method, params):
    import base64
    path=params.get("path")
    if not isinstance(path,str) or not path.startswith("/") or "\x00" in path:
        raise ValueError("Enter an absolute Linux SERVER path")
    path=Path(path)
    if method=="file.download":
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,"rb") as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>LIMIT:raise ValueError("Select a regular file up to 8 MiB")
            content=stream.read(LIMIT+1)
        if len(content)>LIMIT:raise ValueError("Download limit is 8 MiB")
        return {"content":base64.b64encode(content).decode(),"bytes":len(content)}
    encoded=params.get("content")
    if not isinstance(encoded,str) or len(encoded)>((LIMIT+2)//3)*4:raise ValueError("Upload limit is 8 MiB")
    content=base64.b64decode(encoded,validate=True)
    if len(content)>LIMIT:raise ValueError("Upload limit is 8 MiB")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb") as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True);raise
    return {"path":str(path),"bytes":len(content)}

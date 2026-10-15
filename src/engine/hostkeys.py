"""Persist first-contact SSH host keys; never replace a previously trusted key."""
import base64
import hashlib
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
import paramiko

_lock=threading.RLock()

@contextmanager
def locked(path):
    with _lock:
        flags=os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0)
        fd=os.open(str(path)+".sm-lock",flags,0o600)
        with os.fdopen(fd,"r+b") as stream:
            if os.name=="nt":
                import msvcrt
                if os.fstat(stream.fileno()).st_size==0:stream.write(b"0");stream.flush()
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
            try:yield
            finally:
                if os.name=="nt":
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

class AcceptNewHostKey(paramiko.MissingHostKeyPolicy):
    def __init__(self,path,owner):
        self.path=Path(path);self.owner=owner

    def missing_host_key(self,client,hostname,key):
        path=self.path;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with locked(path):
            if path.is_symlink():raise ValueError("SSH known_hosts must not be a symlink")
            keys=paramiko.HostKeys()
            if path.exists():keys.load(str(path))
            existing=keys.lookup(hostname)
            if existing is not None:
                expected=existing.get(key.get_name())
                if expected!=key:raise paramiko.BadHostKeyException(hostname,key,expected or next(iter(existing.values())))
            else:
                keys.add(hostname,key.get_name(),key)
                fd,temp=tempfile.mkstemp(prefix=".known-hosts-",dir=path.parent)
                try:
                    os.close(fd);keys.save(temp)
                    if os.name!="nt":os.chmod(temp,0o600)
                    with open(temp,"r+b") as stream:os.fsync(stream.fileno())
                    os.replace(temp,path)
                finally:
                    if os.path.exists(temp):os.unlink(temp)
                self.owner.host_key_registered=True
            client.get_host_keys().add(hostname,key.get_name(),key)
        self.owner.host_key_fingerprint="SHA256:"+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")

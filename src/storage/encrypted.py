"""Authenticated encryption with atomic writes and a separately held key."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet


def read_secret(path: Path) -> bytes:
    """Read a server secret, rejecting group/world access on Unix."""
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise PermissionError(f"Secret must have mode 0600: {path}")
    return path.read_bytes().strip()


class EncryptedStore:
    def __init__(self, root: Path, key_file: Path):
        self.root = root.resolve()
        if key_file.resolve().is_relative_to(self.root):
            raise ValueError("Keep the encryption key outside the data directory")
        self.cipher = Fernet(read_secret(key_file))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, name: str) -> Path:
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("Storage path must stay inside its root")
        return target

    def write_bytes(self, name: str, data: bytes) -> str:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encrypted = self.cipher.encrypt(data)
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".pending-")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            if os.name == "posix":
                # Persist the rename and newly created backup/job directories.
                directory = target.parent
                while True:
                    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                    if directory == self.root.parent:
                        break
                    directory = directory.parent
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(target)

    def read_bytes(self, name: str) -> bytes:
        return self.cipher.decrypt(self.path(name).read_bytes())

    def write_json(self, name: str, value) -> str:
        return self.write_bytes(name, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))

    def read_json(self, name: str, default=None):
        if not self.path(name).exists():
            return default
        return json.loads(self.read_bytes(name).decode("utf-8"))

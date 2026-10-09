import os
import stat

import pytest
from cryptography.fernet import Fernet
from storage.encrypted import EncryptedStore


@pytest.mark.skipif(os.name != "posix", reason="Directory persistence is checked on Linux")
def test_directory_sync_failure_is_not_reported_as_a_successful_save(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    store = EncryptedStore(tmp_path / "DATA", key)
    original = os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory sync failed")
        original(fd)
    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(OSError, match="directory sync"):
        store.write_bytes("jobs/run.json.enc", b"private payload")
    assert store.read_bytes("jobs/run.json.enc") == b"private payload"
    assert b"private payload" not in store.path("jobs/run.json.enc").read_bytes()
    assert not list(store.root.rglob(".pending-*"))

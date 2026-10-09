import threading
from types import SimpleNamespace
from unittest.mock import Mock
from cryptography.fernet import Fernet
import pytest
from server.service import ManagementService
from storage.encrypted import EncryptedStore


def service():
    instance = ManagementService.__new__(ManagementService)
    instance.lock = threading.RLock()
    instance.summary = lambda job: job
    instance.jobs = {str(index): {"id": str(index), "created_at": f"{index:05d}",
                                "kind": "backup" if index < 120 else "monitoring"}
                     for index in range(250)}
    return instance


def test_backup_history_not_hidden_by_recent_monitoring_jobs():
    instance = service()
    assert all(job["kind"] == "monitoring" for job in instance.dispatch("job.list", {}))
    first = instance.dispatch("job.list", {"kind": "backup"})
    second = instance.dispatch("job.list", {"kind": "backup", "offset": 100})
    assert len(first) == 100 and len(second) == 20
    assert len({job["id"] for job in first + second}) == 120


@pytest.mark.parametrize("offset", [-1, True, "100"])
def test_history_rejects_invalid_offset(offset):
    with pytest.raises(ValueError, match="offset"):
        service().dispatch("job.list", {"offset": offset})


def test_restart_restores_backups_older_than_recent_hundred_jobs(tmp_path, monkeypatch):
    key = tmp_path / "master.key"
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    config = SimpleNamespace(data_directory=tmp_path / "DATA", backup_directory=tmp_path / "BACKUP",
                             key_file=key, ssh_profiles_file=tmp_path / "absent-profiles.json")
    store = EncryptedStore(config.data_directory, key)
    for job in service().jobs.values():
        store.write_json(f"jobs/{job['id']}.json.enc", {**job, "status": "completed"})
    monkeypatch.setattr("server.service.Scheduler", lambda service: Mock())
    restored = ManagementService(config)
    try:
        assert len(restored.jobs) == 250
        first = restored.dispatch("job.list", {"kind": "backup"})
        second = restored.dispatch("job.list", {"kind": "backup", "offset": 100})
        assert len(first) == 100 and len(second) == 20
    finally:
        restored.close()

import threading
from types import SimpleNamespace
from unittest.mock import Mock
from cryptography.fernet import Fernet
import pytest
from server.service import ManagementService
from storage.encrypted import EncryptedStore


def service():
    instance = ManagementService.__new__(ManagementService)
    instance.history_errors = []
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


def test_damaged_history_preserved_and_operations_blocked(tmp_path, monkeypatch):
    key = tmp_path / "master.key"
    key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    config = SimpleNamespace(data_directory=tmp_path / "DATA", backup_directory=tmp_path / "BACKUP",
                             key_file=key, ssh_profiles_file=tmp_path / "absent-profiles.json")
    store = EncryptedStore(config.data_directory, key)
    store.write_json("jobs/good.json.enc", {"id": "good", "kind": "backup", "status": "completed", "created_at": "2026"})
    damaged = store.path("jobs/damaged.json.enc")
    damaged.write_bytes(b"damaged ciphertext")
    monkeypatch.setattr("server.service.Scheduler", lambda service: Mock())
    restored = ManagementService(config)
    try:
        assert list(restored.jobs) == ["good"]
        assert restored.history_errors == [{"file": "damaged.json.enc", "error": "InvalidToken"}]
        with pytest.raises(RuntimeError, match="recovery required"):
            restored.submit("backup", [])
        assert damaged.read_bytes() == b"damaged ciphertext"
    finally:
        restored.close()


@pytest.mark.parametrize("field,value", [("status", []), ("created_at", 42), ("kind", None),
                                        ("results", {}), ("targets", "invalid"), ("done", -1),
                                        ("total", True), ("failed", "1"), ("message", {}), ("status", "unknown")])
def test_malformed_history_is_preserved_without_breaking_startup(tmp_path, monkeypatch, field, value):
    key = tmp_path / "master.key"
    key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    config = SimpleNamespace(data_directory=tmp_path / "DATA", backup_directory=tmp_path / "BACKUP",
                             key_file=key, ssh_profiles_file=tmp_path / "absent-profiles.json")
    store = EncryptedStore(config.data_directory, key)
    good = {"id": "good", "kind": "backup", "status": "completed", "created_at": "2026"}
    store.write_json("jobs/good.json.enc", good)
    store.write_json("jobs/bad.json.enc", {**good, "id": "bad", field: value})
    original = store.path("jobs/bad.json.enc").read_bytes()
    monkeypatch.setattr("server.service.Scheduler", lambda service: Mock())
    restored = ManagementService(config)
    try:
        assert restored.dispatch("job.list", {}) == [good]
        assert restored.history_errors == [{"file": "bad.json.enc", "error": "ValueError"}]
        with pytest.raises(RuntimeError, match="recovery required"):
            restored.submit("backup", [])
        assert store.path("jobs/bad.json.enc").read_bytes() == original
    finally:
        restored.close()


def test_damaged_encrypted_schedule_preserves_original_and_keeps_service_readable(tmp_path):
    key = tmp_path / "master.key"
    key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    config = SimpleNamespace(data_directory=tmp_path / "DATA", backup_directory=tmp_path / "BACKUP",
                             key_file=key, ssh_profiles_file=tmp_path / "absent-profiles.json")
    store = EncryptedStore(config.data_directory, key)
    damaged = store.path("schedules.json.enc"); damaged.write_bytes(b"damaged schedule")
    restored = ManagementService(config)
    try:
        assert restored.dispatch("job.list", {}) == []
        assert restored.scheduler.list() == []
        assert restored.history_errors == [{"file": "schedules.json.enc", "error": "InvalidToken"}]
        with pytest.raises(RuntimeError, match="recovery required"):
            restored.submit("backup", [])
        assert damaged.read_bytes() == b"damaged schedule"
    finally:
        restored.close()

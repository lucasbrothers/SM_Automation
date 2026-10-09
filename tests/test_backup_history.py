import threading
import pytest
from server.service import ManagementService


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

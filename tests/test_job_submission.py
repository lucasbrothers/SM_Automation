"""Ensure submission failures do not occupy active job slots."""
import threading
from unittest.mock import Mock

import pytest
from server.service import ManagementService


def service():
    instance = ManagementService.__new__(ManagementService)
    instance.history_errors = []
    instance.jobs = {}; instance.closed = False; instance.lock = threading.RLock()
    instance.pool = Mock(); instance.data = Mock()
    instance.inventory = lambda: [{"hostname": "lab", "ip": "127.0.0.1", "os": "Ubuntu", "profile": "default"}]
    return instance


def test_failed_persistence_does_not_register_or_dispatch():
    instance = service(); instance.data.write_json.side_effect = OSError("storage failed")
    with pytest.raises(OSError):
        instance.submit("connections", ["lab"])
    assert instance.jobs == {}
    instance.pool.submit.assert_not_called()


def test_executor_failure_records_terminal_state():
    instance = service(); instance.pool.submit.side_effect = RuntimeError("executor unavailable")
    with pytest.raises(RuntimeError):
        instance.submit("connections", ["lab"])
    job = next(iter(instance.jobs.values()))
    assert job["status"] == "failed" and "finished_at" in job
    assert instance.data.write_json.call_count == 2


def test_ssh_apply_requires_existing_completed_plan():
    instance = service()
    with pytest.raises(ValueError, match="completed SSH plan"):
        instance.submit("security_apply", ["lab"], {"plan_id": "a" * 32})
    instance.pool.submit.assert_not_called()

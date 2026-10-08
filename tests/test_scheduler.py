"""Verify scheduling across dispatch failures, restart and inventory changes."""
import copy
from datetime import datetime, timedelta
import threading

import pytest
from server.scheduler import Scheduler


class MemoryData:
    def __init__(self, items=None):
        self.items = items or []

    def read_json(self, *args):
        return copy.deepcopy(self.items)

    def write_json(self, path, items):
        self.items = copy.deepcopy(items)


class Service:
    def __init__(self, items=None):
        self.data = MemoryData(items); self.lock = threading.RLock(); self.jobs = {}; self.count = 0
        self.rows = [{"hostname": "lab", "ip": "127.0.0.1", "os": "Ubuntu", "profile": "default"}]

    def inventory(self):
        return self.rows

    def submit(self, kind, names):
        self.count += 1
        job = {"id": str(self.count), "status": "completed"}
        self.jobs[job["id"]] = job
        return job


@pytest.fixture
def scheduler():
    scheduler = Scheduler(Service()); scheduler.close()
    return scheduler


def future():
    return (datetime.now().astimezone() + timedelta(minutes=5)).isoformat()


def due(scheduler, repeat=0):
    scheduler.create("connections", ["lab"], future(), repeat)
    scheduler.items[0]["next_run"] = (datetime.now().astimezone() - timedelta(seconds=2)).isoformat()


def test_one_off_dispatches_once(scheduler):
    due(scheduler); scheduler.tick(); scheduler.tick()
    assert scheduler.service.count == 1
    assert not scheduler.items[0]["enabled"]


def test_repeating_schedule_skips_missed_intervals(scheduler):
    due(scheduler, 60); scheduler.tick(); scheduler.tick()
    assert scheduler.service.count == 1
    assert datetime.fromisoformat(scheduler.items[0]["next_run"]) > datetime.now().astimezone()


def test_inventory_change_pauses(scheduler):
    due(scheduler); scheduler.service.rows[0] = {**scheduler.service.rows[0], "ip": "127.0.0.2"}
    scheduler.tick()
    assert scheduler.service.count == 0
    assert not scheduler.items[0]["enabled"]


def test_dispatch_failure_does_not_retry(scheduler, monkeypatch):
    due(scheduler)
    def fail(*args):
        raise RuntimeError("uncertain submit")
    monkeypatch.setattr(scheduler.service, "submit", fail)
    scheduler.tick(); scheduler.tick()
    assert not scheduler.items[0]["enabled"]


def test_uncertain_restart_disables_schedule(scheduler):
    due(scheduler); scheduler.items[0]["dispatching"] = True
    restored = Scheduler(Service(scheduler.items)); restored.close(); restored.tick()
    assert not restored.items[0]["enabled"]
    assert restored.service.count == 0


def test_mutating_jobs_cannot_be_scheduled(scheduler):
    with pytest.raises(ValueError):
        scheduler.create("patches", ["lab"], future(), 60)


def test_active_previous_job_does_not_overlap(scheduler):
    due(scheduler, 60)
    scheduler.items[0]["last_job_id"] = "old"
    scheduler.service.jobs["old"] = {"status": "running"}
    scheduler.tick()
    assert scheduler.service.count == 0


def test_failed_create_does_not_leave_executable_schedule(scheduler, monkeypatch):
    def fail(*args):
        raise OSError("storage unavailable")
    monkeypatch.setattr(scheduler.service.data, "write_json", fail)
    with pytest.raises(OSError):
        scheduler.create("connections", ["lab"], future(), 60)
    assert scheduler.items == []


def test_failed_pause_restores_persisted_state(scheduler, monkeypatch):
    item = scheduler.create("connections", ["lab"], future(), 60)
    def fail(*args):
        raise OSError("storage unavailable")
    monkeypatch.setattr(scheduler.service.data, "write_json", fail)
    with pytest.raises(OSError):
        scheduler.change(item["id"], enabled=False)
    assert scheduler.items[0]["enabled"]


def test_failed_delete_keeps_schedule(scheduler, monkeypatch):
    item = scheduler.create("connections", ["lab"], future(), 60)
    def fail(*args):
        raise OSError("storage unavailable")
    monkeypatch.setattr(scheduler.service.data, "write_json", fail)
    with pytest.raises(OSError):
        scheduler.change(item["id"], delete=True)
    assert scheduler.items[0]["id"] == item["id"]

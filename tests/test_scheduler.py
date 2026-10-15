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
        self.history_errors = []
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


@pytest.mark.parametrize("stored", [{"bad": "collection"}, [None], [{"id": "bad"}]])
def test_malformed_schedule_collection_is_preserved_and_blocks_new_work(stored):
    service = Service(stored)
    restored = Scheduler(service); restored.close()
    assert restored.list() == []
    assert service.data.items == stored
    assert service.history_errors == [{"file": "schedules.json.enc", "error": "ValueError"}]
    with pytest.raises(RuntimeError, match="recovery"):
        restored.create("backup", ["lab"], future())


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


@pytest.mark.parametrize("mutation", ["different", "duplicate_hosts", "duplicate_targets", "message", "dispatching", "last_job_id"])
def test_restart_rejects_inconsistent_schedule_targets(scheduler, mutation):
    due(scheduler)
    item = copy.deepcopy(scheduler.items[0])
    if mutation == "different":
        item["hosts"] = ["other-host"]
    elif mutation == "duplicate_hosts":
        item["hosts"] *= 2
    elif mutation == "duplicate_targets":
        item["targets"] *= 2
    else:
        item[mutation] = {"invalid": "type"}
    service = Service([item])
    restored = Scheduler(service); restored.close(); restored.tick()
    assert service.count == 0 and restored.list() == []
    assert service.data.items == [item]
    assert service.history_errors[0]["file"] == "schedules.json.enc"


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


def test_history_recovery_pauses_and_preserves_schedules(scheduler):
    due(scheduler, 60)
    service = Service(scheduler.items)
    service.history_errors = [{"file": "damaged.json.enc"}]
    restored = Scheduler(service); restored.close()
    restored.tick()
    assert not restored.items[0]["enabled"] and service.count == 0
    assert not service.data.items[0]["enabled"]
    with pytest.raises(RuntimeError, match="recovery required"):
        restored.create("connections", ["lab"], future())
    with pytest.raises(RuntimeError, match="recovery required"):
        restored.change(restored.items[0]["id"], enabled=True)
    service.history_errors = []
    restored.tick()
    assert service.count == 0


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
    assert scheduler.failure == "OSError"
    scheduler.items[0]["next_run"] = (datetime.now().astimezone() - timedelta(seconds=2)).isoformat()
    scheduler.tick()
    assert scheduler.service.count == 0


def test_failed_delete_keeps_schedule(scheduler, monkeypatch):
    item = scheduler.create("connections", ["lab"], future(), 60)
    def fail(*args):
        raise OSError("storage unavailable")
    monkeypatch.setattr(scheduler.service.data, "write_json", fail)
    with pytest.raises(OSError):
        scheduler.change(item["id"], delete=True)
    assert scheduler.items[0]["id"] == item["id"]


def test_scheduler_reports_failure_without_exposing_exception_details(scheduler, monkeypatch):
    scheduler.stop.clear()
    monkeypatch.setattr(scheduler.stop, "wait", lambda timeout: scheduler.stop.is_set())
    def fail():
        raise OSError("private storage diagnostic")
    monkeypatch.setattr(scheduler, "tick", fail)
    scheduler.run()
    assert scheduler.stop.is_set() and scheduler.failure == "OSError"


def test_stopped_scheduler_rejects_new_or_resumed_work_but_allows_pause_and_delete(scheduler):
    item = scheduler.create("backup", ["lab"], future())
    scheduler.failure = "OSError"
    with pytest.raises(RuntimeError, match="scheduler stopped"):
        scheduler.create("backup", ["lab"], future())
    with pytest.raises(RuntimeError, match="scheduler stopped"):
        scheduler.change(item["id"], enabled=True)
    assert len(scheduler.items) == 1
    assert not scheduler.change(item["id"], enabled=False)["enabled"]
    scheduler.change(item["id"], delete=True)
    assert scheduler.items == []


def test_cron_dispatch_restart_and_expired_resume(scheduler):
    item=scheduler.create('monitoring',['lab'],cron='*/5 * * * *',cron_timezone='UTC')
    scheduler.items[0]['next_run']=(datetime.now().astimezone()-timedelta(minutes=10)).isoformat()
    scheduler.tick();scheduler.tick()
    assert scheduler.service.count==1 and scheduler.items[0]['enabled']
    assert datetime.fromisoformat(scheduler.items[0]['next_run'])>datetime.now().astimezone()
    restored=Scheduler(Service(scheduler.list()));restored.close()
    assert restored.list()[0]['cron']=='*/5 * * * *' and not restored.recovery_required
    restored.items[0]['enabled']=False
    restored.items[0]['next_run']=(datetime.now().astimezone()-timedelta(minutes=10)).isoformat()
    assert restored.change(item['id'],enabled=True)['enabled']
    assert datetime.fromisoformat(restored.items[0]['next_run'])>datetime.now().astimezone()


def test_update_keeps_id_and_persists_cron(scheduler):
    item=scheduler.create('backup',['lab'],future())
    changed=scheduler.update(item['id'],'monitoring',['lab'],cron='0 9 * * 1-5',cron_timezone='UTC',enabled=False)
    assert changed['id']==item['id'] and not changed['enabled'] and changed['kind']=='monitoring'
    restored=Scheduler(Service(scheduler.list()));restored.close()
    assert restored.list()[0]['cron']=='0 9 * * 1-5'


def test_update_rejects_running_and_rolls_back_failed_save(scheduler,monkeypatch):
    item=scheduler.create('backup',['lab'],future());scheduler.items[0]['last_job_id']='active';scheduler.service.jobs['active']={'status':'running'}
    with pytest.raises(ValueError,match='running'):scheduler.update(item['id'],'monitoring',['lab'],future())
    scheduler.service.jobs['active']['status']='completed'
    def failed(*_):raise OSError('write failed')
    monkeypatch.setattr(scheduler.service.data,'write_json',failed)
    with pytest.raises(OSError):scheduler.update(item['id'],'monitoring',['lab'],future())
    assert scheduler.items[0]['kind']=='backup'


def test_equipment_book_changes_pause_scheduled_work(scheduler):
    book={'id':'book','name':'test','hosts':['lab']};scheduler.service.equipment_book=lambda identity:book
    item=scheduler.create('backup',['lab'],future(),book_id='book')
    book['hosts']=['other'];scheduler.items[0]['next_run']=(datetime.now().astimezone()-timedelta(seconds=2)).isoformat()
    scheduler.tick()
    assert not scheduler.items[0]['enabled'] and scheduler.service.count==0


def test_agent_heartbeat_does_not_invalidate_schedule_but_identity_change_does(scheduler):
    row=scheduler.service.rows[0];row.update(transport='agent',agent_id='a'*32,last_seen='previous',agent_status='online')
    item=scheduler.create('connections',['lab'],future(),60)
    stored=scheduler.items[0];stored['next_run']=(datetime.now().astimezone()-timedelta(seconds=1)).isoformat()
    row.update(last_seen='new heartbeat',agent_status='offline')
    scheduler.tick()
    assert scheduler.service.count==1 and stored['enabled']
    row['agent_id']='b'*32;stored['next_run']=(datetime.now().astimezone()-timedelta(seconds=1)).isoformat()
    scheduler.tick()
    assert scheduler.service.count==1 and not stored['enabled'] and 'Inventory changed' in stored['message']

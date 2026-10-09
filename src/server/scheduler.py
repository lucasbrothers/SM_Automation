"""Encrypted schedules owned by Linux, independent of GUI lifetime."""
from __future__ import annotations

from datetime import datetime, timedelta
import threading
import uuid
import copy
from cryptography.fernet import InvalidToken


class Scheduler:
    def __init__(self, service):
        self.service = service
        self.failure = None
        self.recovery_required = False
        try:
            self.items = service.data.read_json("schedules.json.enc", [])
            if not isinstance(self.items, list) or len(self.items) > 100:
                raise ValueError("Invalid stored schedule collection")
            identities = set()
            for item in self.items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in identities:
                    raise ValueError("Invalid stored schedule identity")
                identities.add(item["id"])
                if item.get("kind") not in {"connections", "backup", "monitoring", "security_audit"} or not isinstance(item.get("enabled"), bool):
                    raise ValueError("Invalid stored schedule operation")
                interval = item.get("interval_seconds")
                if isinstance(interval, bool) or not isinstance(interval, int) or (interval != 0 and not 60 <= interval <= 31536000):
                    raise ValueError("Invalid stored schedule interval")
                if not isinstance(item.get("next_run"), str) or datetime.fromisoformat(item["next_run"]).tzinfo is None:
                    raise ValueError("Invalid stored schedule time")
                if not isinstance(item.get("hosts"), list) or not item["hosts"] or any(not isinstance(host, str) for host in item["hosts"]):
                    raise ValueError("Invalid stored schedule hosts")
                if not isinstance(item.get("targets"), list) or not item["targets"] or any(not isinstance(row, dict) or not isinstance(row.get("hostname"), str) for row in item["targets"]):
                    raise ValueError("Invalid stored schedule targets")
                target_names = [row["hostname"] for row in item["targets"]]
                if len(set(item["hosts"])) != len(item["hosts"]) or len(set(target_names)) != len(target_names) or set(item["hosts"]) != set(target_names):
                    raise ValueError("Stored schedule targets do not match execution hosts")
                if not isinstance(item.get("message", ""), str) or not isinstance(item.get("dispatching", False), bool):
                    raise ValueError("Invalid stored schedule state")
                if item.get("last_job_id") is not None and not isinstance(item["last_job_id"], str):
                    raise ValueError("Invalid stored schedule job reference")
        except (InvalidToken, ValueError, UnicodeError, OSError, TypeError) as exc:
            self.items = []
            self.recovery_required = True
            service.history_errors.append({"file": "schedules.json.enc", "error": type(exc).__name__})
        self.lock = threading.RLock()
        self.stop = threading.Event()
        # An uncertain dispatch after a crash must not be automatically repeated.
        for item in self.items:
            if service.history_errors and item.get("enabled"):
                item.update(enabled=False, dispatching=False, message="History recovery required; review before resuming")
            elif item.get("dispatching"):
                item.update(enabled=False, dispatching=False, message="Interrupted dispatch; inspect job history before resuming")
        self.save()
        self.thread = threading.Thread(target=self.run, name="scheduler", daemon=True)
        self.thread.start()

    def save(self):
        if self.recovery_required:
            return
        self.service.data.write_json("schedules.json.enc", self.items)

    def list(self):
        with self.lock:
            return [dict(item) for item in self.items]

    def create(self, kind, hosts, run_at, interval_seconds=0):
        if self.service.history_errors:
            raise RuntimeError("History recovery required before creating schedules")
        if kind not in {"connections", "backup", "monitoring", "security_audit"}:
            raise ValueError("Schedules support collection, monitoring, audit and backup only")
        timestamp = datetime.fromisoformat(run_at)
        if timestamp.tzinfo is None or timestamp <= datetime.now().astimezone():
            raise ValueError("Choose a future time with an explicit timezone")
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int) or (interval_seconds != 0 and not 60 <= interval_seconds <= 31536000):
            raise ValueError("Repeat interval must be zero (once), or 60 to 31536000 seconds")
        inventory = {row["hostname"]: row for row in self.service.inventory()}
        if not isinstance(hosts, list) or not hosts or any(name not in inventory for name in hosts):
            raise ValueError("Select existing inventory targets")
        with self.lock:
            if len(self.items) >= 100:
                raise ValueError("At most 100 schedules are retained; delete old schedules first")
            item = {"id": uuid.uuid4().hex, "kind": kind, "hosts": list(dict.fromkeys(hosts)),
                    "targets": [inventory[name] for name in dict.fromkeys(hosts)],
                    "next_run": timestamp.isoformat(), "interval_seconds": interval_seconds,
                    "enabled": True, "message": "Waiting on Linux", "last_job_id": None}
            self.items.append(item)
            try:
                self.save()
            except Exception:
                self.items.remove(item)
                raise
            return dict(item)

    def change(self, schedule_id, enabled=None, delete=False):
        if enabled is True and not delete and self.service.history_errors:
            raise RuntimeError("History recovery required before resuming schedules")
        if not isinstance(delete, bool):
            raise ValueError("Delete must be a boolean")
        with self.lock:
            before = copy.deepcopy(self.items)
            item = next(i for i in self.items if i["id"] == schedule_id)
            if delete:
                self.items.remove(item)
            else:
                if not isinstance(enabled, bool):
                    raise ValueError("Enabled must be a boolean")
                if enabled and datetime.fromisoformat(item["next_run"]) <= datetime.now().astimezone():
                    raise ValueError("Expired schedules cannot resume; create a new future schedule")
                item.update(enabled=enabled, message="Waiting on Linux" if enabled else "Paused")
            try:
                self.save()
            except Exception:
                self.items = before
                raise
            return dict(item)

    def tick(self):
        timestamp = datetime.now().astimezone()
        with self.lock:
            for item in self.items:
                if not item["enabled"] or datetime.fromisoformat(item["next_run"]) > timestamp:
                    continue
                with self.service.lock:
                    previous = self.service.jobs.get(item.get("last_job_id"), {})
                    busy = sum(job["status"] in {"queued", "running"} for job in self.service.jobs.values()) >= 2
                if previous.get("status") in {"queued", "running"} or busy:
                    item["message"] = "Waiting for active Linux jobs"; continue
                inventory = {row["hostname"]: row for row in self.service.inventory()}
                if any(inventory.get(row["hostname"]) != row for row in item["targets"]):
                    item.update(enabled=False, message="Inventory changed; create a new schedule"); self.save(); continue
                # Persist intent before dispatch: no duplicate catch-up after an uncertain restart.
                item["dispatching"] = True; self.save()
                try:
                    job = self.service.submit(item["kind"], item["hosts"])
                    item.update(last_job_id=job["id"], dispatching=False, message="Submitted to Linux")
                    if item["interval_seconds"]:
                        item["next_run"] = (timestamp + timedelta(seconds=item["interval_seconds"])).isoformat()
                    else:
                        item["enabled"] = False
                    self.save()
                except Exception:
                    item.update(enabled=False, dispatching=False, message="Dispatch failed; inspect history before creating a new schedule")
                    self.save()

    def run(self):
        while not self.stop.wait(1):
            try:
                self.tick()
            except Exception as exc:
                # A persistence failure stops scheduling until an operator restarts the service.
                self.failure = type(exc).__name__
                self.stop.set()

    def close(self):
        self.stop.set(); self.thread.join(timeout=5)

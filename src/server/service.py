"""Inventory, asynchronous SSH work and encrypted job history."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from backup.collector import backup_server
from account.manager import manage_accounts, validate_options
from patch.manager import validate_options as patch_options, list_updates, make_plan, apply_plan
from core.inventory import ServerRecord
from engine.ssh import SSHClient
from monitoring.collector import collect_linux_snapshot
from monitoring.connections import collect_connections, os_family
from security.audit import audit_linux_server
from storage.encrypted import EncryptedStore, read_secret
from server.scheduler import Scheduler
from security.permissions import secure_ssh_config
from backup.preview import archive_listing
from security.remediation import build_remediation_plan
from security.apply import apply_sshd_settings
from security.plan import verify_observations
from engine.remote import privileged


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def inventory_records(rows):
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("Inventory must contain at most 5000 servers")
    result, seen = [], set()
    for row in rows:
        hostname = str(row.get("hostname", "")).strip()
        address = str(ipaddress.ip_address(str(row.get("ip", "")).strip()))
        platform = str(row.get("os", "")).strip()
        os_family(platform)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}", hostname) or hostname.casefold() in seen:
            raise ValueError("Hostnames must be unique and use letters, digits, dots, underscores or hyphens")
        seen.add(hostname.casefold())
        profile = str(row.get("profile") or "default").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", profile):
            raise ValueError("Invalid SSH profile name")
        result.append({"hostname": hostname, "ip": address, "os": platform, "profile": profile})
    return result


class ManagementService:
    def __init__(self, config):
        self.config = config
        self.data = EncryptedStore(config.data_directory, config.key_file)
        self.backups = EncryptedStore(config.backup_directory, config.key_file)
        self.profiles = (json.loads(read_secret(config.ssh_profiles_file))
                         if config.ssh_profiles_file.exists() else {})
        if not isinstance(self.profiles, dict):
            raise ValueError("SSH profiles must be a JSON object")
        self.lock = threading.RLock()
        self.account_locks = defaultdict(threading.Lock)
        self.jobs = {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="management")
        # Retain past output on disk; never repeat interrupted remote work automatically.
        for path in sorted(self.data.root.glob("jobs/*.json.enc"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            job = self.data.read_json(str(path.relative_to(self.data.root)))
            if job["status"] in {"queued", "running"}:
                job.update(status="interrupted", message="Server restarted; inspect partial artifacts before retrying", finished_at=now())
                self.data.write_json(f"jobs/{job['id']}.json.enc", job)
            self.jobs[job["id"]] = job
        self.scheduler = Scheduler(self)

    def inventory(self):
        with self.lock:
            return self.data.read_json("inventory.json.enc", [])

    def save_inventory(self, rows):
        rows = inventory_records(rows)
        for row in rows:
            if row["profile"] != "default" and row["profile"] not in self.profiles:
                raise ValueError(f"SSH profile is not configured on Linux: {row['profile']}")
        with self.lock:
            self.data.write_json("inventory.json.enc", rows)
        return {"count": len(rows)}

    def summary(self, job):
        return {key: value for key, value in job.items() if key not in {"results", "targets"}}

    def _save(self, job):
        self.data.write_json(f"jobs/{job['id']}.json.enc", job)

    def submit(self, kind, names, options=None):
        if kind not in {"connections", "backup", "monitoring", "security_audit", "security_plan", "security_apply", "security_permissions", "accounts", "patches"}:
            raise ValueError("Unknown job type")
        if not isinstance(names, list) or not names:
            raise ValueError("Select at least one server")
        inventory = self.inventory()
        indexed = {row["hostname"]: row for row in inventory}
        if any(name not in indexed for name in names):
            raise ValueError("A selected server is no longer in the inventory")
        targets = [indexed[name] for name in dict.fromkeys(names)]
        supplied = options or {}
        options = (validate_options(supplied) if kind == "accounts" else
                   patch_options(options or {}) if kind == "patches" else {})
        if kind == "security_apply":
            plan_id = supplied.get("plan_id", "")
            if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
                raise ValueError("SSH apply requires a completed plan ID")
            options = {"plan_id": plan_id}
        if kind in {"accounts", "patches", "security_permissions"} and any(os_family(row["os"]) != "linux" for row in targets):
            raise ValueError("Account and patch management currently support Linux targets")
        with self.lock:
            if kind == "security_apply":
                plan = self.jobs.get(options["plan_id"], {})
                if plan.get("kind") != "security_plan" or plan.get("status") != "completed":
                    raise ValueError("A completed SSH plan is required")
                if sorted(plan["targets"], key=lambda r: r["hostname"]) != sorted(targets, key=lambda r: r["hostname"]):
                    raise ValueError("Targets changed; create a new SSH plan")
                if (datetime.now().astimezone() - datetime.fromisoformat(plan["created_at"])).total_seconds() > 3600:
                    raise ValueError("SSH plan expired; create a new plan")
            if kind == "patches" and options["action"] == "apply":
                plan = self.jobs.get(options["plan_id"], {})
                if plan.get("kind") != "patches" or plan.get("options", {}).get("action") != "plan" or plan.get("status") != "completed":
                    raise ValueError("A completed patch plan is required")
                if sorted(plan["targets"], key=lambda r: r["hostname"]) != sorted(targets, key=lambda r: r["hostname"]):
                    raise ValueError("Targets changed; create a new patch plan")
                if (datetime.now().astimezone() - datetime.fromisoformat(plan["created_at"])).total_seconds() > 3600:
                    raise ValueError("Patch plan expired; create a new plan")
            if self.closed:
                raise RuntimeError("Server is shutting down")
            if sum(job["status"] in {"queued", "running"} for job in self.jobs.values()) >= 2:
                raise RuntimeError("Two jobs are already active; wait for one to finish")
            job = {"id": uuid.uuid4().hex, "kind": kind, "status": "queued", "created_at": now(),
                   "total": len(targets), "done": 0, "failed": 0, "partial": 0,
                   "cancel_requested": False, "cancelled": 0,
                   "targets": targets, "options": options, "message": "Queued on Linux main server", "results": []}
            self.jobs[job["id"]] = job
            try:
                self._save(job)
            except Exception:
                del self.jobs[job["id"]]
                raise
            try:
                self.pool.submit(self._run, job, targets)
            except Exception:
                job.update(status="failed", message="Linux executor rejected the job; no remote operation started", finished_at=now())
                self._save(job)
                raise
            return self.summary(job)

    def _target(self, job, row):
        if job["kind"] in {"security_permissions", "security_apply"}:
            with self.lock:
                target_lock = self.account_locks[row["ip"]]
            with target_lock:
                return self._target_unlocked(job, row)
        if (job["kind"] == "accounts" and job["options"]["action"] != "list") or (job["kind"] == "patches" and job["options"]["action"] == "apply"):
            with self.lock:
                target_lock = self.account_locks[row["ip"]]
            with target_lock:
                return self._target_unlocked(job, row)
        return self._target_unlocked(job, row)

    def _target_unlocked(self, job, row):
        with self.lock:
            if job.get("cancel_requested"):
                return {**row, "status": "cancelled", "message": "Not started: cancellation requested"}
        server = ServerRecord(**{key: row[key] for key in ("hostname", "ip", "os")})
        client = None
        try:
            name = row.get("profile", "default")
            if name != "default" and name not in self.profiles:
                raise ValueError("SSH profile is not configured on the Linux server")
            profile = self.profiles.get(name, {})
            mode = profile.get("privilege", self.config.privilege)
            if mode not in {"sudo", "sudo-su", "direct", "su"}:
                raise ValueError("Invalid SSH profile privilege mode")
            host_config = replace(self.config, privilege=mode)
            key_file = profile.get("key_file", self.config.ssh_key_file)
            client = SSHClient(server.hostname, server.ip, user=profile.get("user", self.config.ssh_user),
                               password=os.environ.get(profile.get("password_env", "SM_AUTOMATION_SSH_PASSWORD")),
                               key_filename=Path(key_file).expanduser() if key_file else None,
                               port=int(profile.get("port", self.config.ssh_port)), timeout=self.config.ssh_timeout)
            family = os_family(server.os)
            kind = job["kind"]
            if kind == "backup":
                result = backup_server(client, server, host_config, self.backups, job["id"],
                                       lambda text: self._progress(job, text))
            elif kind == "connections":
                result = collect_connections(client, family, self.config.ssh_timeout)
                connections = result["connections"]
                result["observed_count"] = len(connections)
                result["connections"] = connections[:5000]
                result["truncated"] = len(connections) > 5000
            elif kind == "monitoring":
                if family != "linux":
                    raise ValueError("Resource monitoring currently supports Linux targets")
                result = collect_linux_snapshot(client).to_dict()
            elif kind == "security_apply":
                with self.lock:
                    planned = next(item["result"] for item in self.jobs[job["options"]["plan_id"]]["results"] if item["hostname"] == row["hostname"])
                    plan = planned["plan"]
                verify_observations(planned["observations"], asdict(audit_linux_server(client, privilege=mode)))
                if plan["status"] == "blocked":
                    raise ValueError("SSH plan is blocked")
                actions = plan["actions"]
                if any(action.get("parameter") == "permitrootlogin" and action.get("current") == "no"
                       and action.get("recommended") != "no" for action in actions):
                    raise ValueError("Disabled root login must remain disabled; regenerate the SSH plan")
                if not actions:
                    result = {"applied": 0, "note": "Policy already satisfied; no files or services changed"}
                else:
                    if mode != "sudo" and not (mode == "direct" and profile.get("user", self.config.ssh_user) == "root"):
                        raise ValueError("SSH apply adapter currently requires sudo or direct root")
                    before = backup_server(client, server, host_config, self.backups, job["id"])
                    if before["status"] != "completed":
                        return {**row, "status": "failed", "error": "Pre-policy backup incomplete", "result": {"backup": before}}
                    with self.lock:
                        if job.get("cancel_requested"):
                            return {**row, "status": "cancelled", "result": {"backup": before}}
                    try:
                        service_name = "ssh" if any(name in server.os.casefold() for name in ("ubuntu", "debian")) else "sshd"
                        output = apply_sshd_settings(client, actions, service_name=service_name,
                                                     allow_includes=planned.get("adapter", {}).get("allow_includes", False),
                                                     discard_backup=True)
                        result = {"applied": len(actions), "output": output, "backup": before}
                    except Exception as exc:
                        return {**row, "status": "failed", "error": str(exc)[:1500], "result": {"backup": before}}
            elif kind == "security_permissions":
                before = backup_server(client, server, host_config, self.backups, job["id"],
                                       lambda text: self._progress(job, text))
                if before["status"] != "completed":
                    return {**row, "status": "failed", "error": "Pre-policy backup incomplete; permissions unchanged", "result": {"backup": before}}
                with self.lock:
                    if job.get("cancel_requested"):
                        return {**row, "status": "cancelled", "result": {"backup": before}}
                try:
                    result = secure_ssh_config(client, mode, self.config.ssh_timeout)
                except Exception as exc:
                    return {**row, "status": "failed", "error": str(exc)[:1500], "result": {"backup": before}}
                result["backup"] = before
            elif kind == "accounts":
                options = job["options"]
                login_user = profile.get("user", self.config.ssh_user)
                if options["action"] != "list":
                    if options["username"] == login_user:
                        raise ValueError("The SSH management account cannot be changed")
                    extra_commands = None
                    if options["action"] == "public_key":
                        from account.keys import key_command
                        extra_commands = {"account_ssh_key_before": key_command(options["username"], "snapshot")}
                    before = backup_server(client, server, host_config, self.backups, job["id"],
                                           lambda text: self._progress(job, text), extra_commands=extra_commands)
                    if before["status"] != "completed":
                        return {**row, "status": "failed", "error": "Pre-change backup incomplete; account unchanged", "result": {"backup": before}}
                    with self.lock:
                        if job.get("cancel_requested"):
                            return {**row, "status": "cancelled", "message": "Cancelled after backup; account unchanged", "result": {"backup": before}}
                    try:
                        result = manage_accounts(client, options, mode, login_user, self.config.ssh_timeout)
                    except Exception as exc:
                        return {**row, "status": "failed", "error": str(exc)[:1500], "result": {"backup": before}}
                    result["backup"] = before
                else:
                    result = manage_accounts(client, options, mode, login_user, self.config.ssh_timeout)
            elif kind == "patches":
                options = job["options"]
                if options["action"] == "list":
                    result = list_updates(client, mode)
                elif options["action"] == "plan":
                    result = make_plan(client, options["packages"], mode)
                else:
                    with self.lock:
                        plan = next(item["result"] for item in self.jobs[options["plan_id"]]["results"] if item["hostname"] == row["hostname"])
                    before = backup_server(client, server, host_config, self.backups, job["id"],
                                           lambda text: self._progress(job, text))
                    if before["status"] != "completed":
                        return {**row, "status": "failed", "error": "Pre-patch backup incomplete; packages unchanged", "result": {"backup": before}}
                    with self.lock:
                        if job.get("cancel_requested"):
                            return {**row, "status": "cancelled", "message": "Cancelled after backup; packages unchanged", "result": {"backup": before}}
                    try:
                        result = apply_plan(client, plan, mode)
                    except Exception as exc:
                        return {**row, "status": "failed", "error": str(exc)[:1500], "result": {"backup": before}}
                    result["backup"] = before
            else:
                if family != "linux":
                    raise ValueError("Security audit currently supports Linux targets")
                result = asdict(audit_linux_server(client, privilege=mode))
                if kind == "security_plan":
                    from security.policy import default_ssh_policy
                    policy = default_ssh_policy()
                    record = {**row, **result, "root_accounts": list(result["root_accounts"]), "status": "passed"}
                    result = {"observations": result, "policy": policy,
                              "plan": build_remediation_plan([record], policy)[0],
                              "note": "Preview only; authentication settings have not been changed"}
                    unsupported = client.execute(privileged("awk '{key=tolower($1); sub(/=.*/, \"\", key)} key == \"include\" || key == \"match\" {print key}' /etc/ssh/sshd_config", mode)).strip()
                    allow_includes = any(name in server.os.casefold() for name in ("ubuntu", "debian"))
                    reason = "Flat SSH configuration"
                    if allow_includes:
                        from security.includes import scan_command
                        try:
                            client.execute(privileged(scan_command(), mode))
                            unsupported = ""
                            reason = "Bounded global Include configuration; conditional Match is unsupported"
                        except Exception:
                            unsupported = "unsupported"
                            reason = "Include scan failed: conditional, external, cyclic or unreadable configuration"
                    elif unsupported:
                        reason = "Include/Match configuration requires a dedicated adapter"
                    result["adapter"] = {"supported": not bool(unsupported), "reason": reason,
                                         "allow_includes": allow_includes and not bool(unsupported)}
                    if unsupported and result["plan"]["actions"]:
                        result["plan"]["status"] = "blocked"
                        result["plan"]["reasons"].append(result["adapter"]["reason"])
            return {**row, "status": result.pop("status", "completed"), "result": result}
        except Exception as exc:
            return {**row, "status": "failed", "error": str(exc)[:1500]}
        finally:
            if client is not None:
                client.close()

    def _progress(self, job, message):
        with self.lock:
            job["message"] = message

    def _run(self, job, targets):
        try:
            with self.lock:
                job.update(status="running", started_at=now())
                self._save(job)
            with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(targets))) as workers:
                futures = [workers.submit(self._target, job, row) for row in targets]
                for future in as_completed(futures):
                    result = future.result()
                    with self.lock:
                        job["results"].append(result)
                        job["done"] += 1
                        job["failed"] += result["status"] == "failed"
                        job["partial"] += result["status"] == "partial"
                        job["cancelled"] = job.get("cancelled", 0) + (result["status"] == "cancelled")
                        job["message"] = f"{job['done']} / {job['total']} servers finished"
                        self._save(job)
            with self.lock:
                status = "failed" if job["failed"] == job["total"] else (
                    "partial" if job["failed"] or job["partial"] else "completed")
                if job.get("cancel_requested"):
                    status = "cancelled"
                    job["message"] = "Cancelled pending targets; started operations finished and results retained"
                job.update(status=status, finished_at=now())
                self._save(job)
        except Exception as exc:
            with self.lock:
                job.update(status="failed", message=f"Job stopped: {type(exc).__name__}", finished_at=now())
                try:
                    self._save(job)
                except OSError:
                    pass

    def dispatch(self, method, params):
        if method == "schedule.list":
            return self.scheduler.list()
        if method == "schedule.create":
            return self.scheduler.create(params["kind"], params["hosts"], params["run_at"], params.get("interval_seconds", 0))
        if method == "schedule.change":
            return self.scheduler.change(params["id"], params.get("enabled"), params.get("delete", False))
        if method == "job.cancel":
            with self.lock:
                job = self.jobs[params["id"]]
                if job["status"] in {"queued", "running"}:
                    job.update(cancel_requested=True, message="Cancellation requested; started operations will finish")
                    self._save(job)
                return self.summary(job)
        if method == "status":
            return {"platform": "Linux main server", "version": "0.2.0", "time": now(),
                    "scheduler_running": self.scheduler.thread.is_alive(),
                    "data_directory": str(self.config.data_directory), "backup_directory": str(self.config.backup_directory),
                    "inventory_count": len(self.inventory()), "encrypted": True}
        if method == "inventory.list":
            return self.inventory()
        if method == "inventory.save":
            return self.save_inventory(params["servers"])
        if method == "inventory.import":
            content = params["csv"]
            return self.save_inventory(list(csv.DictReader(io.StringIO(content.lstrip("\ufeff")))))
        if method == "job.start":
            return self.submit(params["kind"], params["hosts"], params.get("options"))
        if method in {"backup.preview", "backup.contents"}:
            path = params["path"]
            endings = (".tar.enc",) if method == "backup.contents" else (".txt.enc", ".json.enc")
            if not isinstance(path, str) or not path.endswith(endings):
                raise ValueError("Only text and JSON artifacts support preview; export archives on Linux")
            if self.backups.path(path).stat().st_size > 96 * 1024 * 1024:
                raise ValueError("Artifact is too large to preview; export it on Linux")
            content = self.backups.read_bytes(path)
            if method == "backup.contents":
                return archive_listing(content)
            return {"text": content[:65536].decode("utf-8", errors="replace"),
                    "truncated": len(content) > 65536, "bytes": len(content)}
        with self.lock:
            if method == "job.list":
                return [self.summary(job) for job in sorted(self.jobs.values(), key=lambda item: item["created_at"], reverse=True)[:100]]
            if method == "job.get":
                return self.summary(self.jobs[params["id"]])
            if method == "job.result":
                job = self.jobs[params["id"]]
                offset = max(0, int(params.get("offset", 0)))
                return {"items": job["results"][offset:offset + 1], "total": len(job["results"])}
        raise ValueError("Unknown API method")

    def close(self):
        self.closed = True
        self.scheduler.close()
        self.pool.shutdown(wait=True)

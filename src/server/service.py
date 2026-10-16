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
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from cryptography.fernet import InvalidToken

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
        if not isinstance(row, dict):
            raise ValueError("Each inventory row must be an object")
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


def inventory_csv(content):
    if not isinstance(content, str):
        raise ValueError("Inventory CSV must be text")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    headers = [name.strip().casefold() for name in (reader.fieldnames or [])]
    if len(headers) != len(set(headers)):
        raise ValueError("Inventory CSV contains duplicate column names")
    if not {"hostname", "ip", "os"}.issubset(headers):
        raise ValueError("Inventory CSV requires hostname, ip and os columns; profile is optional")
    reader.fieldnames = headers
    rows = []
    for row in reader:
        if None in row:
            raise ValueError(f"Inventory CSV row {reader.line_num} has extra values")
        if any(not row.get(field) or not row[field].strip() for field in ("hostname", "ip", "os")):
            raise ValueError(f"Inventory CSV row {reader.line_num} requires hostname, ip and os values")
        try:
            normalized = inventory_records([row])[0]
        except ValueError as exc:
            raise ValueError(f"Inventory CSV row {reader.line_num}: {exc}") from exc
        rows.append(normalized)
        if len(rows) > 5000:
            raise ValueError("Inventory must contain at most 5000 servers")
    return inventory_records(rows)


def load_ssh_profiles(path):
    profiles = json.loads(read_secret(path)) if path.exists() else {}
    if not isinstance(profiles, dict):
        raise ValueError("SSH profiles must be a JSON object")
    for name, profile in profiles.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or not isinstance(profile, dict):
            raise ValueError("SSH profile names and records are invalid")
        if set(profile) - {"user", "port", "key_file", "privilege", "password_env"}:
            raise ValueError(f"SSH profile {name} has unsupported fields; passwords belong in environment variables")
        if "user" in profile and (not isinstance(profile["user"], str) or not profile["user"].strip()
                                   or len(profile["user"]) > 256 or any(ord(char) < 32 for char in profile["user"])):
            raise ValueError(f"SSH profile {name}: invalid user")
        if "port" in profile and (isinstance(profile["port"], bool) or not isinstance(profile["port"], int)
                                   or not 1 <= profile["port"] <= 65535):
            raise ValueError(f"SSH profile {name}: port must be an integer from 1 to 65535")
        if "privilege" in profile and (not isinstance(profile["privilege"], str) or profile["privilege"] not in {"sudo", "sudo-su", "direct", "su"}):
            raise ValueError(f"SSH profile {name}: invalid privilege mode")
        key = profile.get("key_file")
        if key is not None and (not isinstance(key, str) or not key.startswith(("/", "~/"))
                                or any(ord(char) < 32 for char in key)):
            raise ValueError(f"SSH profile {name}: key_file must be a Linux absolute or ~/ path")
        if "password_env" in profile and (not isinstance(profile["password_env"], str) or
                                           not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", profile["password_env"])):
            raise ValueError(f"SSH profile {name}: invalid password environment variable name")
    return profiles


def verify_inventory_profiles(rows, profiles):
    for row in rows:
        if row["profile"] != "default" and row["profile"] not in profiles:
            raise ValueError(f"SSH profile is not configured on Linux: {row['profile']}")


class ManagementService:
    def __init__(self, config):
        self.config = config
        self.data = EncryptedStore(config.data_directory, config.key_file)
        self.backups = EncryptedStore(config.backup_directory, config.key_file)
        self.profiles = load_ssh_profiles(config.ssh_profiles_file)
        self.lock = threading.RLock()
        self.command_passwords = {}
        self.ssh_slots=threading.BoundedSemaphore(getattr(config,"max_workers",5))
        self.heavy_slots=threading.BoundedSemaphore(1)
        self.report_slots=threading.BoundedSemaphore(1);self.report_cache={}
        self.account_locks = defaultdict(threading.Lock)
        self.jobs = {}
        self.history_errors = []
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="management")
        # Retain past output on disk; never repeat interrupted remote work automatically.
        for path in sorted(self.data.root.glob("jobs/*.json.enc"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                job = self.data.read_json(str(path.relative_to(self.data.root)))
                if not isinstance(job, dict) or job.get("id") != path.name.removesuffix(".json.enc") or not all(
                        isinstance(job.get(field), str) and job[field] for field in ("status", "kind", "created_at")):
                    raise ValueError("Invalid stored job record")
                if any(field in job and not isinstance(job[field], list) for field in ("results", "targets")):
                    raise ValueError("Invalid stored job collections")
                if not all(field in job for field in ("done", "total", "results")):
                    raise ValueError("Stored job is missing required progress or results")
                if job["status"] not in {"queued", "running", "completed", "partial", "failed", "cancelled", "interrupted"}:
                    raise ValueError("Invalid stored job status")
                for field in ("done", "total", "failed", "partial", "cancelled"):
                    if field in job and (isinstance(job[field], bool) or not isinstance(job[field], int) or job[field] < 0):
                        raise ValueError("Invalid stored job progress")
                if job["done"] > job["total"] or len(job["results"]) != job["done"]:
                    raise ValueError("Stored job progress does not match saved results")
                if sum(job.get(field, 0) for field in ("failed", "partial", "cancelled")) > job["done"]:
                    raise ValueError("Stored job result counts exceed completed targets")
                if "message" in job and not isinstance(job["message"], str):
                    raise ValueError("Invalid stored job message")
            except (InvalidToken, ValueError, UnicodeError, OSError) as exc:
                self.history_errors.append({"file": path.name, "error": type(exc).__name__})
                continue
            if job["status"] in {"queued", "running"}:
                job.update(status="interrupted", message="Server restarted; inspect partial artifacts before retrying", finished_at=now())
                self.data.write_json(f"jobs/{job['id']}.json.enc", job)
            self.jobs[job["id"]] = job
        from server.agents import AgentManager
        self.agents = AgentManager(self)
        self.scheduler = Scheduler(self)

    def inventory(self):
        with self.lock:
            rows = self.data.read_json("inventory.json.enc", [])
            return self.agents.decorate(rows) if hasattr(self,"agents") else rows

    def save_inventory(self, rows):
        rows = inventory_records(rows)
        verify_inventory_profiles(rows, self.profiles)
        with self.lock:
            if hasattr(self,"agents"):
                names={row["hostname"] for row in rows}
                for name,identity in self.agents.bindings.items():
                    if name not in names and self.agents.device(identity):self.agents.revoke(identity)
            self.data.write_json("inventory.json.enc", rows)
        return {"count": len(rows)}

    def client_credentials(self, hostname):
        row = next((r for r in self.inventory() if r["hostname"] == hostname), None)
        if row is None:
            raise ValueError("Select an inventory CLIENT")
        saved = self.data.read_json("client-credentials.json.enc", {}).get(hostname, {})
        if saved.get("ip") != row["ip"]:
            saved = {}
        profile = self.profiles.get(row.get("profile", "default"), {})
        return row, saved, profile

    def credentials_get(self, hostname):
        with self.lock:
            row, saved, profile = self.client_credentials(hostname)
            return {"hostname": hostname, "ip": row["ip"],
                    "user": saved.get("user", profile.get("user", self.config.ssh_user)),
                    "port": saved.get("port", profile.get("port", self.config.ssh_port)),
                    "password_saved": bool(saved.get("password"))}

    def credentials_save(self, params):
        hostname = params.get("hostname"); user = params.get("user"); port = params.get("port")
        password = params.get("password", ""); use_password = params.get("use_password", False)
        if not isinstance(user, str) or not user.strip() or len(user) > 256 or any(ord(c) < 32 for c in user):
            raise ValueError("Invalid CLIENT login account")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("SSH port must be 1–65535")
        if not isinstance(password, str) or len(password) > 4096 or "\x00" in password or not isinstance(use_password, bool):
            raise ValueError("Invalid CLIENT password settings")
        with self.lock:
            row, saved, _ = self.client_credentials(hostname)
            if any(j["status"] in {"queued", "running"} and any(t["hostname"] == hostname for t in j["targets"]) for j in self.jobs.values()):
                raise ValueError("Wait for this CLIENT's active jobs before changing login settings")
            if use_password and not (password or saved.get("password")):
                raise ValueError("Enter a CLIENT password")
            records = self.data.read_json("client-credentials.json.enc", {})
            records[hostname] = {"ip": row["ip"], "user": user.strip(), "port": port,
                                 "password": (password or saved.get("password", "")) if use_password else ""}
            self.data.write_json("client-credentials.json.enc", records)
            return self.credentials_get(hostname)

    def summary(self, job):
        return {key: value for key, value in job.items() if key not in {"results", "targets"}}

    def _result(self,row):
        if row.get("result_ref"):return self.data.read_json(row["result_ref"])
        return row

    def _store_result(self,job,row):
        if job["kind"] == "connections":row={**row,"observed_at":now()}
        if job["kind"] not in {"backup","backup_compare","connections","monitoring","ci_inventory"}:return row
        path="results/"+job["id"]+"/"+row["hostname"]+".json.enc"
        self.data.write_json(path,row)
        small={key:value for key,value in row.items() if key!="result"}
        small["result_ref"]=path
        if job["kind"]=="backup_compare":small["result"]=row.get("result",{})
        return small

    def _save(self, job):
        self.data.write_json(f"jobs/{job['id']}.json.enc", job)
        if job["kind"]=="connections":self.connection_cache_index=None

    def cached_connections(self,params):
        offset=params.get("offset",0)
        if type(offset) is not int or offset<0:raise ValueError("Invalid cache offset")
        with self.lock:
            if getattr(self,"connection_cache_index",None) is None:
                index={}
                for job in self.jobs.values():
                    if job["kind"]!="connections":continue
                    for row in job["results"]:
                        key=tuple(row.get(k,"") for k in ("hostname","ip","os"))
                        # Older data has no per-target observation time: label the job time explicitly.
                        stamp=row.get("observed_at") or job.get("finished_at") or job.get("started_at") or job["created_at"]
                        if key not in index or stamp>index[key][0]:index[key]=(stamp,row,not bool(row.get("observed_at")))
                self.connection_cache_index=index
            rows=[]
            for host in self.inventory():
                key=tuple(host.get(k,"") for k in ("hostname","ip","os"))
                cached=self.connection_cache_index.get(key)
                if cached:rows.append(cached)
            if offset>=len(rows):return {"items":[],"total":len(rows)}
            stamp,row,legacy=rows[offset]
            return {"items":[{**self._result(row),"observed_at":stamp,"time_is_job_time":legacy}],"total":len(rows)}

    def equipment_book(self,identity):
        from server.equipment import get
        with self.lock:return get(self.data,identity,self.inventory())

    def submit(self, kind, names, options=None, book_id=None):
        if self.history_errors:
            raise RuntimeError("Job history recovery required on Linux; new operations are disabled")
        if kind not in {"connections", "backup", "monitoring", "security_audit", "security_plan", "security_apply", "security_permissions", "accounts", "patches", "command", "transfer", "deploy_key", "backup_compare", "ci_inventory"}:
            raise ValueError("Unknown job type")
        book=self.equipment_book(book_id) if book_id else None
        if book:
            if names and set(names)!=set(book["hosts"]):raise ValueError("Equipment book membership changed; refresh targets")
            names=list(book["hosts"])
        if not isinstance(names, list) or not names:
            raise ValueError("Select at least one server")
        inventory = self.inventory()
        indexed = {row["hostname"]: row for row in inventory}
        if any(name not in indexed for name in names):
            raise ValueError("A selected server is no longer in the inventory")
        targets = [indexed[name] for name in dict.fromkeys(names)]
        supplied = options or {}
        if kind in {"accounts","patches"} and any(os_family(row["os"]) in {"windows","aix"} for row in targets) and supplied.get("action","list")!="list":
            raise ValueError("Windows/AIX accounts and patches are read-only; select Linux targets for changes")
        spread=supplied.get("spread_seconds",60 if len(targets)>50 else 0)
        if type(spread) is not int or not 0<=spread<=3600:raise ValueError("Spread must be 0–3600 seconds")
        options = (validate_options(supplied) if kind == "accounts" else
                   patch_options(options or {}) if kind == "patches" else {})
        if kind == "backup_compare":
            baseline_id=supplied.get("baseline_job_id")
            with self.lock:
                baseline=self.jobs.get(baseline_id,{})
                if baseline.get("kind")!="backup" or baseline.get("status") in {"queued","running"}:raise ValueError("Select a finished backup as baseline")
            options={"baseline_job_id":baseline_id}
        if kind == "transfer":
            from server.files import validate
            options = validate(supplied)
            if len(targets)>1 and options["direction"]=="upload" and "{hostname}" not in options["server_path"]:
                raise ValueError("Multiple CLIENT uploads require {hostname} in the SERVER destination path")
        if kind == "command":
            command = supplied.get("command")
            if not isinstance(command, str) or not command.strip() or len(command) > 16384 or "\x00" in command:
                raise ValueError("Command must be nonempty text up to 16384 characters")
            secret = supplied.get("root_password", "")
            if not isinstance(secret, str) or len(secret) > 4096 or any(c in secret for c in "\r\n\x00"):
                raise ValueError("Invalid root password")
            options = {"command": command}
        if kind in {"backup","backup_compare"}:
            secret=supplied.get("root_password","")
            if not isinstance(secret,str) or len(secret)>4096 or any(c in secret for c in "\r\n\x00"):raise ValueError("Invalid root password")
        if kind == "security_apply":
            plan_id = supplied.get("plan_id", "")
            if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
                raise ValueError("SSH apply requires a completed plan ID")
            options = {"plan_id": plan_id}
        if ((kind in {"accounts", "patches"} and any(os_family(row["os"]) not in {"linux","windows","aix"} for row in targets)) or (kind == "security_permissions" and any(os_family(row["os"]) != "linux" for row in targets))):
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
                if any(not row.get("result", {}).get("apply_supported", True) for row in plan.get("results", [])):
                    raise ValueError("This patch plan has no supported application adapter")
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
                   "targets": targets, "options": options, "message": "SERVER accepted job; awaiting worker", "results": []}
            job["spread_seconds"]=spread
            if book:job.update(equipment_book_id=book["id"],equipment_book_name=book["name"])
            self.jobs[job["id"]] = job
            if kind in {"command","backup","backup_compare"}:
                self.command_passwords[job["id"]] = supplied.get("root_password", "")
            try:
                self._save(job)
            except Exception:
                del self.jobs[job["id"]]
                self.command_passwords.pop(job["id"], None)
                raise
            try:
                self.pool.submit(self._run, job, targets)
            except Exception:
                self.command_passwords.pop(job["id"], None)
                job.update(status="failed", message="Linux executor rejected the job; no remote operation started", finished_at=now())
                self._save(job)
                raise
            return self.summary(job)

    def _backup(self,*args,**kwargs):
        with getattr(self,"heavy_slots",nullcontext()):return backup_server(*args,**kwargs)

    def baseline_configuration(self,job,row):
        with self.lock:
            baseline=self.jobs[job["options"]["baseline_job_id"]]
            baseline_row=next((r for r in baseline["results"] if r["hostname"]==row["hostname"] and r.get("ip")==row["ip"] and r.get("os")==row["os"]),None)
            if baseline_row:baseline_row=self._result(baseline_row)
            artifact=next((a for a in baseline_row.get("result",{}).get("artifacts",[]) if a["name"]=="configuration_files"),None) if baseline_row else None
            if not artifact:raise ValueError("기준 백업에 해당 장비·주소·OS의 설정 파일이 없습니다")
            return artifact

    def _target(self,job,row):
        if row.get("transport") == "agent":
            return self.agents.execute(job,row)
        with getattr(self,"ssh_slots",nullcontext()):
            with (getattr(self,"heavy_slots",nullcontext()) if job["kind"] in {"backup_compare"} else nullcontext()):
                return self._target_inner(job,row)

    def _spread_target(self,job,row,index,total,started):
        due=started+job.get("spread_seconds",0)*index/max(1,total-1)
        while time.monotonic()<due:
            with self.lock:
                if job.get("cancel_requested"):return {**row,"status":"cancelled","message":"Cancelled before connection"}
            time.sleep(min(1,max(0,due-time.monotonic())))
        return self._target(job,row)

    def _target_inner(self, job, row):
        if job["kind"] in {"security_permissions", "security_apply", "command", "transfer", "deploy_key"}:
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
            if not key_file:
                generated = self.config.key_file.parent / "client-login.key"
                if job["kind"] == "deploy_key" or generated.exists():
                    key_file = generated
            with self.lock:
                current_target, saved_credentials, _ = self.client_credentials(server.hostname)
                if current_target["ip"] != row["ip"]:
                    raise ValueError("CLIENT address changed; submit a new job")
            password = saved_credentials.get("password") or os.environ.get(profile.get("password_env", "SM_AUTOMATION_SSH_PASSWORD"))
            client = SSHClient(server.hostname, server.ip,
                               user=saved_credentials.get("user", profile.get("user", self.config.ssh_user)),
                               password=password,
                               key_filename=None if saved_credentials.get("password") else (Path(key_file).expanduser() if key_file else None),
                               port=saved_credentials.get("port", int(profile.get("port", self.config.ssh_port))), timeout=self.config.ssh_timeout)
            client.accept_new_host_key = job["kind"] == "deploy_key"
            family = os_family(server.os)
            kind = job["kind"]
            if kind == "ci_inventory":
                from ci.collector import collect
                result = collect(client, family, login_password=password or "")
                with self.lock:
                    self.ci_registry().observe(row, result)
            elif kind == "deploy_key":
                from server.key_deploy import deploy
                result = deploy(client, Path(key_file).expanduser())
            elif kind == "transfer":
                from server.files import transfer
                transfer_options={key:value.replace("{hostname}",server.hostname) if isinstance(value,str) else value for key,value in job["options"].items()}
                result = transfer(client, transfer_options)
            elif kind == "command":
                if family not in {"linux", "aix"}:
                    raise ValueError("Root commands support Linux/AIX CLIENTs")
                result = client.execute_root(job["options"]["command"], password or "", self.command_passwords.get(job["id"], ""))
                result["status"] = "completed" if result["exit_code"] == 0 else "failed"
            elif kind == "backup_compare":
                from backup.compare import current_compare
                from engine.remote import capture_root
                artifact=self.baseline_configuration(job,row)
                runner=None if family=="windows" else lambda command:capture_root(client,command,login_password=password or "",root_password=self.command_passwords.get(job["id"],""),timeout=host_config.backup_timeout,max_bytes=host_config.max_capture_mb*1024*1024)
                result=current_compare(client,server,host_config,self.backups,artifact,job["id"],lambda text:self._progress(job,text),runner=runner)
            elif kind == "backup":
                from engine.remote import capture_root
                runner=None if family=="windows" else lambda command:capture_root(client,command,login_password=password or "",root_password=self.command_passwords.get(job["id"],""),timeout=host_config.backup_timeout,max_bytes=host_config.max_capture_mb*1024*1024)
                result = self._backup(client, server, host_config, self.backups, job["id"],
                                       lambda text: self._progress(job, text),runner=runner)
            elif kind == "connections":
                result = collect_connections(client, family, self.config.ssh_timeout)
                connections = result["connections"]
                result["observed_count"] = len(connections)
                result["connections"] = connections[:5000]
                result["truncated"] = len(connections) > 5000
            elif kind == "monitoring":
                if family == "aix":
                    from monitoring.aix import resources
                    result=resources(client)
                elif family == "windows":
                    from monitoring.windows_queries import collect_query
                    result=collect_query(client,"monitoring",{})
                elif family == "linux":result = collect_linux_snapshot(client).to_dict()
                else:raise ValueError("Unsupported resource monitoring OS")
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
                    if mode != "sudo" and not (mode == "direct" and client.user == "root"):
                        raise ValueError("SSH apply adapter currently requires sudo or direct root")
                    before = self._backup(client, server, host_config, self.backups, job["id"])
                    if before["status"] != "completed":
                        return {**row, "status": "failed", "error": "Pre-policy backup incomplete", "result": {"backup": before}}
                    with self.lock:
                        if job.get("cancel_requested"):
                            return {**row, "status": "cancelled", "result": {"backup": before}}
                    try:
                        service_name = "ssh" if any(name in server.os.casefold() for name in ("ubuntu", "debian")) else "sshd"
                        output = apply_sshd_settings(client, actions, service_name=service_name,
                                                     allow_includes=planned.get("adapter", {}).get("allow_includes", False),
                                                     discard_backup=True, privilege=mode)
                        result = {"applied": len(actions), "output": output, "backup": before}
                    except Exception as exc:
                        return {**row, "status": "failed", "error": str(exc)[:1500], "result": {"backup": before}}
            elif kind == "security_permissions":
                before = self._backup(client, server, host_config, self.backups, job["id"],
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
            elif family == "aix" and kind in {"accounts","patches"}:
                from monitoring.aix import accounts,patches
                result=(accounts if kind=="accounts" else patches)(client,job["options"])
            elif family == "windows" and kind in {"accounts","patches"}:
                from monitoring.windows_queries import collect_query
                result=collect_query(client,kind,job["options"])
            elif kind == "accounts":
                options = job["options"]
                login_user = client.user
                if options["action"] != "list":
                    if options["username"] == login_user:
                        raise ValueError("The SSH management account cannot be changed")
                    extra_commands = None
                    if options["action"] == "public_key":
                        from account.keys import key_command
                        extra_commands = {"account_ssh_key_before": key_command(options["username"], "snapshot")}
                    before = self._backup(client, server, host_config, self.backups, job["id"],
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
                    if options.get("files"):
                        from patch.local_files import make_plan as file_plan
                        result = file_plan(client, options["files"], mode)
                    else:
                        result = make_plan(client, options["packages"], mode)
                else:
                    with self.lock:
                        plan = next(item["result"] for item in self.jobs[options["plan_id"]]["results"] if item["hostname"] == row["hostname"])
                    before = self._backup(client, server, host_config, self.backups, job["id"],
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
                    allow_includes = True
                    reason = "Flat SSH configuration"
                    if allow_includes:
                        from security.includes import scan_command
                        try:
                            client.execute(privileged(scan_command(), mode))
                            unsupported = ""
                            reason = "Bounded global Include configuration; conditional Match is unsupported"
                        except Exception:
                            allow_includes = False
                            reason = ("Include scan failed: conditional, external, cyclic or unreadable configuration"
                                      if unsupported else "Flat SSH configuration; system Python Include scanner unavailable")
                    elif unsupported:
                        reason = "Include/Match configuration requires a dedicated adapter"
                    result["adapter"] = {"supported": not bool(unsupported), "reason": reason,
                                         "allow_includes": allow_includes and not bool(unsupported)}
                    if unsupported and result["plan"]["actions"]:
                        result["plan"]["status"] = "blocked"
                        result["plan"]["reasons"].append(result["adapter"]["reason"])
            return {**row, "status": result.pop("status", "completed"), "result": result}
        except Exception as exc:
            if job["kind"] == "ci_inventory":
                with self.lock:
                    self.ci_registry().observe(row, error=str(exc))
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
                job.update(status="running", started_at=now(), message="SERVER started target processing")
                self._save(job)
            started=time.monotonic()
            for index,row in enumerate(targets):
                if row.get("transport")=="agent" and job["kind"] not in {"backup","backup_compare","accounts","patches","monitoring"}:
                    try:
                        with self.lock:self.agents.prepare(job,row,index,len(targets))
                    except (ValueError,OSError):pass  # Per-target execution records the error.
            with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(targets))) as workers:
                futures = {workers.submit(self._spread_target, job, row, index, len(targets), started) for index,row in enumerate(targets)}
                for future in as_completed(futures):
                    result = future.result();futures.remove(future)
                    with self.lock:
                        job["results"].append(self._store_result(job,result))
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

        finally:
            with self.lock:
                self.command_passwords.pop(job["id"], None)

    def ci_registry(self):
        if not hasattr(self, "_ci_registry"):
            from ci.registry import CIRegistry
            self._ci_registry = CIRegistry(self.data)
        return self._ci_registry

    def dispatch(self, method, params):
        if method.startswith("agent."):
            with self.lock:
                if method=="agent.policy.get":return dict(self.agents.policy)
                if method=="agent.policy.save":return self.agents.configure(params)
                if method=="agent.list":return self.agents.listing()
                if method=="agent.revoke":return self.agents.revoke(params.get("id"),bool(params.get("remove",False)))
                if method=="agent.server_identity":
                    from cryptography import x509
                    from cryptography.hazmat.primitives import hashes
                    certificate=x509.load_pem_x509_certificate(self.config.tls_cert.read_bytes())
                    return {"sha256":certificate.fingerprint(hashes.SHA256()).hex(),"port":self.config.listen_port}
            raise ValueError("Unknown agent administration method")
        if method == "ci.list":
            with self.lock:
                return self.ci_registry().listing(self.inventory(), params)
        if method == "ci.update":
            with self.lock:
                return self.ci_registry().update(self.inventory(), params.get("hosts"), params.get("patch"))
        if method=="backup.comparison":
            with self.lock:
                job=self.jobs[params["job_id"]]
                if job["kind"]!="backup_compare":raise ValueError("Not a comparison job")
                row=next((r for r in job["results"] if r["hostname"]==params["hostname"]),None)
                if not row or row["status"]!="completed":raise ValueError("Comparison is not available")
                path=row["result"]["report_path"]
            offset=params.get("offset",0);limit=params.get("limit",50)
            if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError("Invalid comparison page")
            with self.report_slots:
                cached=self.report_cache.get(path)
                if cached and cached[0]>time.monotonic():result=cached[1]
                else:
                    result=self.backups.read_json(path)
                    if len(self.report_cache)>=2:self.report_cache.pop(next(iter(self.report_cache)))
                    self.report_cache[path]=(time.monotonic()+30,result)
            files=result["files"]
            if params.get("changes_only",True):files=[f for f in files if f["status"]!="unchanged"]
            return {"items":files[offset:offset+limit],"total":len(files)}
        if method=="equipment.book.list":
            from server.equipment import books
            with self.lock:return books(self.data)
        if method in {"equipment.book.save","equipment.book.delete"}:
            from server.equipment import change
            with self.lock:return change(self.data,method,params,self.inventory())
        if method in {"command.saved.list", "command.saved.save", "command.saved.delete"}:
            from server.commands import library
            with self.lock:
                return library(self.data, method, params)
        if method.startswith("media."):
            from server.media import handle
            return handle(method, params)
        if method.startswith("file."):
            from server.files import gui_transfer
            return gui_transfer(method, params)
        if method == "gui.account.list":
            with self.lock:
                return [{"id": name, "role": value.get("role", "admin")} for name, value in self.data.read_json("gui-accounts.json.enc", {}).items()]
        if method == "gui.account.save":
            from server.auth import save_account
            with self.lock:
                return save_account(self.data, params.get("username"), params.get("password"), params.get("role"))
        if method == "client.credentials.get":
            return self.credentials_get(params.get("hostname"))
        if method == "client.credentials.save":
            return self.credentials_save(params)
        if method == "schedule.list":
            rows=self.scheduler.list()
            with self.lock:
                for row in rows:
                    row["last_job_status"]=self.jobs.get(row.get("last_job_id"),{}).get("status","")
            return rows
        if method == "schedule.create":
            return self.scheduler.create(params["kind"], params.get("hosts",[]), params.get("run_at"), params.get("interval_seconds", 0), params.get("cron"), params.get("cron_timezone", "Asia/Seoul"),params.get("equipment_book_id"),params.get("enabled",True))
        if method == "schedule.update":
            return self.scheduler.update(params["id"],params["kind"],params.get("hosts",[]),params.get("run_at"),params.get("interval_seconds",0),params.get("cron"),params.get("cron_timezone","Asia/Seoul"),params.get("enabled"),params.get("equipment_book_id"))
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
                    "scheduler_error": self.scheduler.failure,
                    "data_directory": str(self.config.data_directory), "backup_directory": str(self.config.backup_directory),
                    "inventory_count": len(self.inventory()), "encrypted": True,
                    "history_errors": self.history_errors, "operations_enabled": not self.history_errors}
        if method == "connections.cached":
            return self.cached_connections(params)
        if method == "inventory.list":
            return self.inventory()
        if method == "ssh.profiles":
            return sorted(set(self.profiles) | {"default"})
        if method == "inventory.save":
            return self.save_inventory(params["servers"])
        if method == "inventory.import":
            return self.save_inventory(inventory_csv(params["csv"]))
        if method == "job.start":
            return self.submit(params["kind"], params.get("hosts"), params.get("options"),params.get("equipment_book_id"))
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
                offset = params.get("offset", 0)
                if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                    raise ValueError("Job list offset must be a nonnegative integer")
                kind = params.get("kind")
                if kind is not None and kind not in {"backup"}:
                    raise ValueError("Unsupported job history filter")
                jobs = sorted((job for job in self.jobs.values() if kind is None or job["kind"] == kind),
                              key=lambda item: (item["created_at"], item["id"]), reverse=True)
                return [self.summary(job) for job in jobs[offset:offset + 100]]
            if method == "job.get":
                return self.summary(self.jobs[params["id"]])
            if method == "job.result":
                job = self.jobs[params["id"]]
                offset = params.get("offset", 0)
                if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                    raise ValueError("Job result offset must be a nonnegative integer")
                size=params.get("page_size",1);hosts=params.get("hosts")
                if type(size) is not int or not 1<=size<=50:raise ValueError("Invalid result page size")
                results=job["results"]
                if hosts is not None:
                    if not isinstance(hosts,list) or any(not isinstance(h,str) for h in hosts):raise ValueError("Invalid result host filter")
                    wanted=set(hosts);results=[r for r in results if r["hostname"] in wanted]
                # Large per-target results stay on the existing single-target page path.
                if job["kind"] not in {"monitoring","backup_compare","backup"}:size=1
                return {"items":[self._result(row) for row in results[offset:offset+size]],"total":len(results)}
        raise ValueError("Unknown API method")

    def close(self):
        self.closed = True
        self.scheduler.close()
        self.pool.shutdown(wait=True)

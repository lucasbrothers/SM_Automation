"""Capture OS files and command output into encrypted Linux-side backups."""
from __future__ import annotations

from datetime import datetime
import re

from backup.profiles import AIX_PATHS, LINUX_PATHS, commands, unix_archive, windows_files
from engine.remote import capture, privileged
from monitoring.connections import os_family


def backup_server(client, server, config, store, run_id: str, progress=None, extra_commands=None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}", server.hostname):
        raise ValueError("Hostname cannot be used as a backup folder")
    family = os_family(server.os)
    prefix = f"{datetime.now():%Y-%m-%d}/{server.hostname}/{run_id}"
    manifest = {"hostname": server.hostname, "ip": server.ip, "os": server.os,
                "started_at": datetime.now().astimezone().isoformat(), "artifacts": [], "status": "running"}
    steps = commands(family)
    archive = windows_files() if family == "windows" else unix_archive(AIX_PATHS if family == "aix" else LINUX_PATHS)
    steps = {"configuration_files": archive, **steps}
    steps.update(extra_commands or {})
    for index, (name, command) in enumerate(steps.items(), 1):
        if progress:
            progress(f"{server.hostname}: {name} ({index}/{len(steps)})")
        record = {"name": name, "status": "failed"}
        try:
            if family != "windows":
                command = privileged(command, config.privilege)
            result = capture(client, command, timeout=config.backup_timeout,
                             max_bytes=config.max_capture_mb * 1024 * 1024)
            extension = "tar" if name == "configuration_files" and family != "windows" else "txt"
            if name == "configuration_files" and family == "windows":
                extension = "json"
            filename = f"{prefix}/{name}.{extension}.enc"
            store.write_bytes(filename, result.stdout)
            warnings = [line for line in result.stderr.splitlines() if line.startswith("Missing optional path: ")]
            unexpected = [line for line in result.stderr.splitlines() if line.strip() and not line.startswith("Missing optional path: ")]
            record.update(path=filename, size=len(result.stdout), exit_code=result.exit_code,
                          warnings=warnings,
                          status="completed" if result.exit_code == 0 and not unexpected else "partial")
            store.write_json(f"{prefix}/{name}.metadata.json.enc", {
                "command": command, "exit_code": result.exit_code, "stderr": result.stderr,
                "captured_at": datetime.now().astimezone().isoformat(),
            })
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)[:1000]
        manifest["artifacts"].append(record)
        store.write_json(f"{prefix}/manifest.json.enc", manifest)
    statuses = [item["status"] for item in manifest["artifacts"]]
    manifest["status"] = "completed" if all(value == "completed" for value in statuses) else (
        "failed" if all(value == "failed" for value in statuses) else "partial")
    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    store.write_json(f"{prefix}/manifest.json.enc", manifest)
    return {"status": manifest["status"], "directory": str(store.path(prefix)),
            "artifact_count": len(manifest["artifacts"]), "artifacts": manifest["artifacts"]}

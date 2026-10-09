"""Exercise global Include apply and reconnect rollback on authorized WSL only."""
import hashlib
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup.collector import backup_server
from common.config import load_config
from core.inventory import ServerRecord
from engine.ssh import SSHClient, SSHCommandError
from security import apply
from security.includes import scan_command
from storage.encrypted import EncryptedStore


def main():
    if sys.platform != "linux" or os.geteuid() != 0 or "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():
        raise RuntimeError("This integration check requires the authorized local WSL root environment")
    config = load_config(Path("/opt/SM_Automation/config/app.local.json"))
    client = SSHClient("wsl-ubuntu", "127.0.0.1", user="root", key_filename=config.ssh_key_file)
    try:
        client.execute(scan_command())
        before = backup_server(client, ServerRecord("wsl-ubuntu", "127.0.0.1", "Ubuntu 26.04"),
                               config, EncryptedStore(config.backup_directory, config.key_file), uuid.uuid4().hex)
        assert before["status"] == "completed", before["status"]
        actions = [{"type": "set_sshd_option", "parameter": "pubkeyauthentication", "current": "yes", "recommended": "yes"}]
        existing = set(Path("/etc/ssh").glob(".sm_automation.*"))
        output = apply.apply_sshd_settings(client, actions, service_name="ssh", allow_includes=True, discard_backup=True)
        assert "temporary_backup=removed" in output
        assert set(Path("/etc/ssh").glob(".sm_automation.*")) == existing
        print("PASS: encrypted backup, Include-preserving write, ssh reload and fresh key connection")
        digest = hashlib.sha256(Path("/etc/ssh/sshd_config").read_bytes()).digest()
        original = apply.SSHClient
        class FailedProbe:
            def __init__(self, *args, **kwargs):
                pass
            def execute(self, command):
                raise SSHCommandError("Controlled reconnect failure")
            def close(self):
                pass
        apply.SSHClient = FailedProbe
        try:
            try:
                apply.apply_sshd_settings(client, actions, service_name="ssh", allow_includes=True, discard_backup=True)
            except SSHCommandError as exc:
                assert "original configuration restored" in str(exc)
            else:
                raise AssertionError("Controlled probe failure did not trigger rollback")
        finally:
            apply.SSHClient = original
        assert hashlib.sha256(Path("/etc/ssh/sshd_config").read_bytes()).digest() == digest
        assert set(Path("/etc/ssh").glob(".sm_automation.*")) == existing
        client.execute("sshd -t && systemctl is-active ssh")
        probe = SSHClient("wsl-ubuntu", "127.0.0.1", user="root", key_filename=config.ssh_key_file)
        try:
            probe.execute("true")
        finally:
            probe.close()
        print("PASS: controlled reconnect failure restored exact configuration and SSH access")
    finally:
        client.close()


if __name__ == "__main__":
    main()

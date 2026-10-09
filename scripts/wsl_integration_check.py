"""Exercise the authorized local WSL service from a Windows client."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from desktop.client import ConnectionSettings, ServerClient


def wsl_read(path):
    return subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "cat", path])


def main():
    parser = argparse.ArgumentParser(description="Test local WSL only; credentials stay in memory")
    parser.add_argument("--host", default="172.22.194.8")
    parser.add_argument("--secure-ssh-config", action="store_true", help="Back up and apply mode 600 to the authorized WSL SSH configuration")
    args = parser.parse_args()
    token = wsl_read("/root/.config/sm-automation/api.token").decode().strip()
    with tempfile.TemporaryDirectory(prefix="sm-wsl-") as directory:
        certificate = Path(directory) / "ca.crt"
        certificate.write_bytes(wsl_read("/root/.config/sm-automation/ca.crt"))
        client = ServerClient(ConnectionSettings(args.host, 7443, str(certificate), token))
        status = client.call("status")
        assert status["encrypted"] and status["platform"] == "Linux main server"
        print("PASS: Windows client connected to Linux over verified TLS")
        rejected = ServerClient(ConnectionSettings(args.host, 7443, str(certificate), "invalid-token"))
        try:
            rejected.call("status")
        except RuntimeError:
            print("PASS: invalid access token rejected")
        else:
            raise AssertionError("Invalid token accepted")
        inventory = client.call("inventory.list")
        targets = [row for row in inventory if row["hostname"] == "wsl-ubuntu" and row["ip"] == "127.0.0.1"]
        assert len(targets) == 1, "Authorized loopback lab target not found"
        kinds = ["connections", "monitoring", "security_audit", "backup"]
        if args.secure_ssh_config:
            kinds += ["security_permissions", "security_audit"]
        for position, kind in enumerate(kinds):
            job = client.call("job.start", kind=kind, hosts=["wsl-ubuntu"])
            deadline = time.monotonic() + 300
            while job["status"] in {"queued", "running"}:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{kind} did not complete; inspect Linux job history")
                time.sleep(0.5)
                job = client.call("job.get", id=job["id"])
            results = client.results(job["id"])
            assert results and results[0]["status"] != "failed", results
            if kind == "connections":
                assert results[0]["result"]["connections"], "Active SSH connection was not observed"
            if kind == "security_permissions":
                assert results[0]["result"]["mode_owner"].startswith("600 root ")
                assert results[0]["result"]["backup"]["status"] == "completed"
            if kind == "security_audit" and args.secure_ssh_config and position == len(kinds) - 1:
                assert results[0]["result"]["sshd_config_mode"].startswith("600 root ")
            if kind == "backup":
                artifacts = results[0]["result"]["artifacts"]
                required = {"configuration_files", "account_expiry_chage", "account_sudo_privileges"}
                assert required <= {item["name"] for item in artifacts}
                expiry = next(item for item in artifacts if item["name"] == "account_expiry_chage")
                preview = client.call("backup.preview", path=expiry["path"])
                assert "root" in preview["text"]
                archive = next(item for item in artifacts if item["name"] == "configuration_files")
                contents = client.call("backup.contents", path=archive["path"])
                assert "etc/sudoers" in contents["text"]
                print(f"PASS: backup artifacts={len(artifacts)}, status={job['status']}, expiry preview readable")
            else:
                print(f"PASS: {kind}, status={job['status']}")
        print("Integration checks finished; no credentials written to the Windows project")


if __name__ == "__main__":
    main()

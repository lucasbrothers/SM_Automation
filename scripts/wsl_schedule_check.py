"""Exercise encrypted schedules, service restart and cooperative cancellation on WSL only."""
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import tempfile
import time

from wsl_integration_check import wsl_read, ConnectionSettings, ServerClient


def main():
    command = ["wsl", "-d", "Ubuntu", "-u", "root", "--"]
    address = subprocess.check_output(command + ["hostname", "-I"], text=True).split()[0]
    with tempfile.TemporaryDirectory(prefix="sm-schedule-") as directory:
        ca = Path(directory) / "ca.crt"; ca.write_bytes(wsl_read("/root/.config/sm-automation/ca.crt"))
        token = wsl_read("/root/.config/sm-automation/api.token").decode().strip()
        client = ServerClient(ConnectionSettings(address, 7443, str(ca), token))
        assert any(row["hostname"] == "wsl-ubuntu" and row["ip"] == "127.0.0.1" for row in client.call("inventory.list"))
        ids = []
        try:
            scheduled = client.call("schedule.create", kind="connections", hosts=["wsl-ubuntu"], run_at=(datetime.now().astimezone() + timedelta(seconds=2)).isoformat())
            ids.append(scheduled["id"])
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                item = next(s for s in client.call("schedule.list") if s["id"] == scheduled["id"])
                if item["last_job_id"]:
                    job = client.call("job.get", id=item["last_job_id"])
                    if job["status"] == "completed":
                        break
                time.sleep(.2)
            else:
                raise TimeoutError("Scheduled connection job did not complete")
            assert not item["enabled"]
            paused = client.call("schedule.create", kind="monitoring", hosts=["wsl-ubuntu"], run_at=(datetime.now().astimezone() + timedelta(minutes=5)).isoformat(), interval_seconds=60)
            ids.append(paused["id"])
            client.call("schedule.change", id=paused["id"], enabled=False)
            assert wsl_read("/opt/SM_Automation/DATA/schedules.json.enc").startswith(b"gAAAA")
            subprocess.run(command + ["systemctl", "restart", "sm-automation.service"], check=True)
            stored = next(s for s in client.call("schedule.list") if s["id"] == paused["id"])
            assert not stored["enabled"]
            client.call("schedule.change", id=paused["id"], enabled=True)
            client.call("schedule.change", id=paused["id"], enabled=False)
            job = client.call("job.start", kind="backup", hosts=["wsl-ubuntu"])
            client.call("job.cancel", id=job["id"])
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                job = client.call("job.get", id=job["id"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(.2)
            assert job["status"] == "cancelled" and job["cancel_requested"]
            print("PASS: scheduled WSL collection, encrypted persistence across Linux restart, pause/resume and cooperative cancellation")
        finally:
            for schedule_id in ids:
                client.call("schedule.change", id=schedule_id, delete=True)


if __name__ == "__main__":
    main()

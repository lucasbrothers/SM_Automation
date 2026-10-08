"""Verify the patch pipeline with an already-installed version on local WSL."""
import subprocess
import tempfile
import time
from pathlib import Path

from wsl_integration_check import wsl_read, ConnectionSettings, ServerClient


def main():
    command = ["wsl", "-d", "Ubuntu", "-u", "root", "--"]
    address = subprocess.check_output(command + ["hostname", "-I"], text=True).split()[0]
    version = subprocess.check_output(command + ["dpkg-query", "-W", "net-tools"], text=True).split()[1]
    with tempfile.TemporaryDirectory(prefix="sm-patch-") as directory:
        ca = Path(directory) / "ca.crt"; ca.write_bytes(wsl_read("/root/.config/sm-automation/ca.crt"))
        token = wsl_read("/root/.config/sm-automation/api.token").decode().strip()
        client = ServerClient(ConnectionSettings(address, 7443, str(ca), token))
        assert any(row["hostname"] == "wsl-ubuntu" and row["ip"] == "127.0.0.1" for row in client.call("inventory.list"))

        def run(options):
            job = client.call("job.start", kind="patches", hosts=["wsl-ubuntu"], options=options)
            deadline = time.monotonic() + 180
            while job["status"] in {"queued", "running"}:
                if time.monotonic() > deadline:
                    raise TimeoutError("Inspect Linux patch history before retrying")
                time.sleep(.2); job = client.call("job.get", id=job["id"])
            rows = client.results(job["id"])
            assert job["status"] == "completed", rows
            return job, rows[0]["result"]

        _, result = run({"action": "list"})
        assert isinstance(result["packages"], list)
        plan, result = run({"action": "plan", "packages": ["net-tools=" + version]})
        assert result["operations"] == [] and result["pins"] == ["net-tools=" + version]
        _, result = run({"action": "apply", "plan_id": plan["id"]})
        assert result["backup"]["status"] == "completed"
        after = subprocess.check_output(command + ["dpkg-query", "-W", "net-tools"], text=True).split()[1]
        assert version == after
        print("PASS: TLS patch query, exact-version plan, encrypted pre-patch backup and no-change apply on WSL")


if __name__ == "__main__":
    main()

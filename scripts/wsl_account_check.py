"""Exercise account jobs only on the authorized loopback WSL lab."""
import subprocess
import json
import tempfile
import time
from pathlib import Path

from wsl_integration_check import wsl_read, ConnectionSettings, ServerClient


def main():
    address = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"], text=True).split()[0]
    username = "smtest_" + str(int(time.time()))
    with tempfile.TemporaryDirectory(prefix="sm-account-") as directory:
        ca = Path(directory) / "ca.crt"
        ca.write_bytes(wsl_read("/root/.config/sm-automation/ca.crt"))
        token = wsl_read("/root/.config/sm-automation/api.token").decode().strip()
        client = ServerClient(ConnectionSettings(address, 7443, str(ca), token))
        targets = client.call("inventory.list")
        assert any(row["hostname"] == "wsl-ubuntu" and row["ip"] == "127.0.0.1" for row in targets)

        def run(action, **extra):
            job = client.call("job.start", kind="accounts", hosts=["wsl-ubuntu"], options={"action": action, "username": username, **extra})
            deadline = time.monotonic() + 180
            while job["status"] in {"queued", "running"}:
                if time.monotonic() > deadline:
                    raise TimeoutError("Account job timed out; inspect Linux history before retrying")
                time.sleep(.2)
                job = client.call("job.get", id=job["id"])
            return job, client.results(job["id"])[0]

        created = False
        try:
            job, row = run("list")
            assert job["status"] == "completed"
            assert not any(a["username"] == username for a in row["result"]["accounts"])
            job, row = run("create", sr="SR-WSL-TEST", full_name="Temporary Integration Account")
            assert job["status"] == "completed", row
            created = True
            assert row["result"]["backup"]["status"] == "completed"
            public_key = wsl_read("/root/.ssh/sm_automation_wsl.pub").decode().strip()
            for position in range(2):
                job, row = run("public_key", public_key=public_key)
                assert job["status"] == "completed", row
                before = next(item for item in row["result"]["backup"]["artifacts"] if item["name"] == "account_ssh_key_before")
                snapshot = json.loads(client.call("backup.preview", path=before["path"])["text"])
                assert snapshot["exists"] == bool(position)
                assert ("already present" if position else "installed") in row["result"]["output"]
            installed = wsl_read(f"/home/{username}/.ssh/authorized_keys").decode().splitlines()
            assert len(installed) == 1 and installed[0].split() == public_key.split()[:2]
            metadata = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "stat", "-c", "%a %U", f"/home/{username}/.ssh", f"/home/{username}/.ssh/authorized_keys"], text=True).splitlines()
            assert metadata == ["700 " + username, "600 " + username], metadata
            print("PASS: public-key install, idempotence, encrypted prior-key snapshot and owner/permissions")
            logged_in = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-i", "/root/.ssh/sm_automation_wsl", username + "@127.0.0.1", "id -un"], text=True).strip()
            assert logged_in == username
            password_state = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "passwd", "-S", username], text=True).split()[1]
            assert password_state == "L", password_state
            print("PASS: fresh SSH key login to provisioned account; password remains locked")
            job, row = run("password_age", max_days="90")
            assert job["status"] == "completed", row
            assert any("Maximum number" in line and line.strip().endswith("90") for line in row["result"]["output"].splitlines()), row
            job, row = run("expiry", expiry_date="2030-12-31")
            assert job["status"] == "completed" and "Dec 31, 2030" in row["result"]["output"], row
            job, row = run("expiry", expiry_date="never")
            assert job["status"] == "completed", row
            assert any("Account expires" in line and "never" in line for line in row["result"]["output"].splitlines()), row
            job, row = run("groups", groups="users")
            assert job["status"] == "completed" and "users" in row["result"]["output"], row
            job, row = run("remove_groups", groups="users")
            assert job["status"] == "completed", row
            assert "users" not in row["result"]["output"].splitlines()[-1].split(), row
            job, row = run("primary_group", groups="users")
            assert job["status"] == "completed", row
            job, row = run("remove_groups", groups="users")
            assert job["status"] == "failed" and "Cannot remove primary group" in row["error"], row
            job, row = run("primary_group", groups=username)
            assert job["status"] == "completed", row
            for action, fields in [("modify", {"sr": "SR-WSL-TEST", "full_name": "Updated Test Account"}), ("lock", {})]:
                job, row = run(action, **fields)
                assert job["status"] == "completed", row
            job, row = run("unlock")
            assert job["status"] == "failed" and "previously set password" in row["error"]
            job, row = run("list")
            account = next(a for a in row["result"]["accounts"] if a["username"] == username)
            assert "Updated Test Account" in account["comment"]
            assert int(account["uid"]) >= 1000
            print("PASS: account create, modify, list, lock and passwordless unlock rejection; encrypted pre-change backups")
        finally:
            if created:
                job, row = run("delete")
                assert job["status"] == "completed", row
                job, row = run("list")
                assert not any(a["username"] == username for a in row["result"]["accounts"])
                print("PASS: temporary account deleted; home retained at /home/" + username)


if __name__ == "__main__":
    main()

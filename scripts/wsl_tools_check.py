"""Validate commands and CLIENT/SERVER transfer on authorized loopback WSL only."""
import sys
import tempfile
import time
import uuid
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from desktop.client import ConnectionSettings, ServerClient

def read(path):
    return subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "cat", path])

def main():
    host = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"], text=True).split()[0]
    with tempfile.TemporaryDirectory() as directory:
        ca = Path(directory) / "ca.crt"; ca.write_bytes(read("/root/.config/sm-automation/ca.crt"))
        client = ServerClient(ConnectionSettings(host, 7443, str(ca), read("/root/.config/sm-automation/api.token").decode().strip()))
        inventory = client.call("inventory.list")
        assert any(row["hostname"] == "wsl-ubuntu" and row["ip"] == "127.0.0.1" for row in inventory)
        current = client.call("client.credentials.get", hostname="wsl-ubuntu")
        assert "password" not in current
        if not current["password_saved"]:
            saved = client.call("client.credentials.save", hostname="wsl-ubuntu", user=current["user"], port=current["port"], use_password=False)
            assert saved == current and "password" not in saved
        print("PASS: CLIENT login settings API never returns passwords")
        def run(kind, options):
            job = client.call("job.start", kind=kind, hosts=["wsl-ubuntu"], options=options)
            deadline = time.monotonic() + 60
            while job["status"] in {"queued", "running"}:
                assert time.monotonic() < deadline
                time.sleep(.2); job = next(row for row in client.call("job.list") if row["id"] == job["id"])
            return job, client.results(job["id"])
        root_job, root_rows = run("command", {"command": "id -u"})
        assert root_job["status"] == "completed" and root_rows[0]["result"]["stdout"].strip() == "0"
        job, rows = run("command", {"command": "printf command-ok; printf diagnostic >&2; exit 7"})
        assert job["status"] == "failed"
        result = rows[0]["result"]
        assert result["stdout"] == "command-ok" and result["stderr"].endswith("diagnostic") and result["exit_code"] == 7
        from PySide6.QtWidgets import QApplication
        from desktop.main import Console
        app = QApplication.instance() or QApplication([])
        window = Console(); window.display_command_results(rows, job)
        assert window.pages.currentIndex() == 8
        assert window.command_results_table.item(0, 1).text() == "Failed"
        assert window.command_results_table.item(0, 3).text() == "command-ok"
        window.command_results_table.selectRow(0)
        assert "diagnostic" in window.command_details.toPlainText()
        window.close()
        print("PASS: selected CLIENT command stdout/stderr/exit status visible in Commands GUI")
        prefix = "/tmp/sm-transfer-" + uuid.uuid4().hex
        source, remote, returned = prefix + "-server", prefix + "-client", prefix + "-returned"
        try:
            job, _ = run("command", {"command": "printf 'round-trip-data' > " + source})
            assert job["status"] == "completed"
            options = {"direction": "download", "server_path": source, "client_path": remote}
            job, rows = run("transfer", options); assert job["status"] == "completed", rows
            job, _ = run("transfer", {"direction": "upload", "server_path": returned, "client_path": remote})
            assert job["status"] == "completed" and read(returned) == b"round-trip-data"
            job, _ = run("transfer", options); assert job["status"] == "failed"
            assert read(remote) == b"round-trip-data"
            print("PASS: SERVER to CLIENT and CLIENT to SERVER round trip; existing destination preserved")
        finally:
            subprocess.check_call(["wsl", "-d", "Ubuntu", "-u", "root", "--", "rm", "-f", "--", source, remote, returned])
if __name__ == "__main__":
    main()

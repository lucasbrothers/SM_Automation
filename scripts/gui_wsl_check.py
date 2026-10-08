"""Exercise native GUI event handling against the real WSL TLS server."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QPushButton
from desktop.client import ConnectionSettings, ServerClient
from desktop.main import Console, STYLE


def main():
    def read(path):
        return subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "cat", path])
    address = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"], text=True).split()[0]
    with tempfile.TemporaryDirectory(prefix="sm-gui-check-") as directory:
        ca = Path(directory) / "ca.crt"; ca.write_bytes(read("/root/.config/sm-automation/ca.crt"))
        token = read("/root/.config/sm-automation/api.token").decode().strip()
        app = QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setStyle("Fusion"); app.setStyleSheet(STYLE)
        window = Console(); window.show()
        window.connect_to(ServerClient(ConnectionSettings(address, 7443, str(ca), token)))
        stage, deadline, passed = [0], time.monotonic() + 60, [False]
        timer = QTimer()
        def tick():
            if time.monotonic() > deadline:
                print("FAIL: GUI timed out: " + window.status_line.text()); app.exit(1); return
            if stage[0] == 0 and window.servers:
                assert window.servers[0]["hostname"] == "wsl-ubuntu"
                window.navigate(1)
                window.select_all.setChecked(False)
                assert window.checked_hosts() == []
                window.select_all.setChecked(True)
                assert window.checked_hosts() == ["wsl-ubuntu"]
                control = next(item for item in window.findChildren(QPushButton) if item.text() == "Collect connections")
                control.click(); stage[0] = 1
            elif stage[0] == 1 and window.connection_results:
                assert window.connection_table.rowCount() > 0
                assert window.graph.scene().items()
                print("PASS: native GUI TLS connect, select-all, job submission, polling, connection table and mind map")
                window.navigate(4)
                control = next(item for item in window.findChildren(QPushButton) if item.text() == "Run account operation")
                control.click(); stage[0] = 2
            elif stage[0] == 2 and window.account_table.rowCount():
                print("PASS: native Accounts page submits Linux job and displays real account rows")
                passed[0] = True; app.quit()
        timer.timeout.connect(tick); timer.start(100)
        result = app.exec()
        return 0 if passed[0] else (result or 1)


if __name__ == "__main__":
    raise SystemExit(main())

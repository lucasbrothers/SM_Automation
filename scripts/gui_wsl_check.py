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
from PySide6.QtWidgets import QApplication, QPushButton, QTreeWidget, QPlainTextEdit, QMessageBox
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
        def unexpected_warning(parent, title, message):
            print("FAIL: " + title + ": " + message[:200])
            app.exit(1)
            return QMessageBox.StandardButton.Ok
        QMessageBox.warning = unexpected_warning
        for name in ("segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setStyle("Fusion"); app.setStyleSheet(STYLE)
        window = Console(); window.show()
        window.connect_to(ServerClient(ConnectionSettings(address, 7443, str(ca), token)))
        stage, deadline, passed = [0], time.monotonic() + 90, [False]
        backup_dialog = [None]
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
                window.account_action.setCurrentIndex(window.account_action.findData("create"))
                assert window.account_fields["sr"].isVisible() and not window.account_fields["groups"].isVisible()
                window.account_action.setCurrentIndex(window.account_action.findData("public_key"))
                assert window.account_fields["public_key"].isVisible() and not window.account_fields["sr"].isVisible()
                window.account_action.setCurrentIndex(window.account_action.findData("expiry"))
                assert window.account_fields["expiry_date"].isVisible() and not window.account_fields["sr"].isVisible()
                window.account_action.setCurrentIndex(window.account_action.findData("list"))
                window.navigate(5)
                control = next(item for item in window.findChildren(QPushButton) if item.text() == "Query updates")
                control.click(); stage[0] = 3
            elif stage[0] == 3 and window.patch_output.toPlainText():
                version = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "dpkg-query", "-W", "net-tools"], text=True).split()[1]
                window.patch_packages.setText("net-tools=" + version)
                control = next(item for item in window.findChildren(QPushButton) if item.text() == "Preview patch plan")
                control.click(); stage[0] = 4
            elif stage[0] == 4 and window.patch_plan_id and window.patch_apply.isEnabled():
                assert window.patch_table.rowCount() == 1
                print("PASS: native Patches page queries updates and displays a reviewed exact-version plan")
                original = window.display_schedules
                def loaded_schedules(rows):
                    original(rows); window.schedule_table.setProperty("loaded", True)
                window.display_schedules = loaded_schedules
                window.navigate(6)
                stage[0] = 5
            elif stage[0] == 5 and window.schedule_table.property("loaded"):
                assert window.schedule_table.columnCount() == 6
                print("PASS: native Schedules page loads Linux schedules and displays scheduling controls")
                window.start_job("security_plan"); stage[0] = 6
            elif stage[0] == 6 and any(job["id"] == window.active_job and job["status"] == "completed" for job in window.jobs):
                stage[0] = 7
                def check_plan(rows):
                    dialog = window.security_plan_dialog(rows, window.active_job, True)
                    apply_button = next(item for item in dialog.findChildren(QPushButton) if item.text() == "Apply reviewed SSH plan")
                    assert apply_button.isEnabled(), rows
                    dialog.close()
                    window.select_all.setChecked(False)
                    dialog = window.security_plan_dialog(rows, window.active_job, True)
                    apply_button = next(item for item in dialog.findChildren(QPushButton) if item.text() == "Apply reviewed SSH plan")
                    assert not apply_button.isEnabled()
                    dialog.close()
                    print("PASS: native SSH plan table and selection mismatch protection")
                    window.select_all.setChecked(True)
                    window.navigate(7); window.start_job("monitoring"); stage[0] = 8
                window.work(lambda: window.client.results(window.active_job), check_plan)
            elif stage[0] == 8 and window.resource_loaded_job == window.active_job and window.resource_table.rowCount():
                assert window.resource_table.cellWidget(0, 2) is not None
                assert window.resource_table.cellWidget(0, 3) is not None
                window.resource_auto.setChecked(True)
                assert window.resource_timer.isActive()
                window.resource_auto.setChecked(False)
                assert not window.resource_timer.isActive()
                print("PASS: native resource metrics, memory/disk bars and automatic refresh control")
                window.start_job("backup"); stage[0] = 9
            elif stage[0] == 9 and any(job["id"] == window.active_job and job["kind"] == "backup" and job["status"] == "completed" for job in window.jobs):
                stage[0] = 10
                def check_backup(rows):
                    dialog = window.backup_results_dialog(rows)
                    backup_dialog[0] = dialog
                    dialog.show()
                    tree = dialog.findChild(QTreeWidget)
                    server = tree.topLevelItem(0)
                    assert server.childCount() == 11, rows
                    archive = next(server.child(index) for index in range(server.childCount())
                                   if server.child(index).text(0) == "configuration_files")
                    assert any(archive.child(index).text(0).startswith("Missing optional path:")
                               for index in range(archive.childCount()))
                    metadata = archive.child(archive.childCount() - 1)
                    assert metadata.text(3).endswith("configuration_files.metadata.json.enc")
                    tree.itemDoubleClicked.emit(metadata, 0)
                    stage[0] = 11
                window.work(lambda: window.client.results(window.active_job), check_backup)
            elif stage[0] == 11 and '"exit_code"' in backup_dialog[0].findChild(QPlainTextEdit).toPlainText():
                text = backup_dialog[0].findChild(QPlainTextEdit).toPlainText()
                assert '"stderr"' in text and "Missing optional path:" in text
                dialog = backup_dialog[0]
                tree = dialog.findChild(QTreeWidget)
                artifact = tree.topLevelItem(0).child(0)
                pending = []
                original_work = window.work
                try:
                    window.work = lambda fn, loaded: pending.append(loaded)
                    tree.itemDoubleClicked.emit(artifact, 0)
                    tree.itemDoubleClicked.emit(artifact.child(artifact.childCount() - 1), 0)
                finally:
                    window.work = original_work
                editor = dialog.findChild(QPlainTextEdit)
                pending[1]({"text": "latest diagnostic", "truncated": False})
                pending[0]({"text": "stale artifact", "truncated": False})
                assert editor.toPlainText() == "latest diagnostic"
                backup_dialog[0].close()
                pending[1]({"text": "late closed-dialog result", "truncated": False})
                assert editor.toPlainText() == "latest diagnostic"
                print("PASS: native backup details, optional-path warnings and Linux-decrypted command diagnostics")
                print("PASS: delayed backup preview responses cannot overwrite current or closed views")
                window.navigate(2)
                control = next(item for item in window.findChildren(QPushButton) if item.text() == "Refresh backup history")
                control.click(); stage[0] = 12
            elif stage[0] == 12 and window.backup_history_offset:
                assert all(job["kind"] == "backup" for job in window.backup_jobs)
                assert len(window.backup_jobs) >= window.backup_history_offset
                previous = set(window.backup_history)
                window.set_jobs([job for job in window.jobs if job["kind"] != "backup"])
                assert set(window.backup_history) == previous
                window.disconnect_server()
                assert not window.backup_history and window.backup_history_offset == 0
                print("PASS: real filtered backup history button, polling preservation and disconnect reset")
                passed[0] = True; app.quit()
        timer.timeout.connect(tick); timer.start(100)
        result = app.exec()
        return 0 if passed[0] else (result or 1)


if __name__ == "__main__":
    raise SystemExit(main())

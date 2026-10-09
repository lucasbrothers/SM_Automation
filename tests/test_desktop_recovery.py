from unittest.mock import Mock
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox
from desktop.main import Console, InventoryDialog
from desktop.graph import ConnectionMap


def test_schedule_action_uses_selected_identity_after_reordering(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Console(); window.client = Mock()
    def schedule(identity):
        return {"id": identity, "next_run": "2026-10-09T16:00:00", "kind": "backup", "hosts": ["lab"],
                "interval_seconds": 60, "enabled": True, "message": ""}
    window.display_schedules([schedule("selected"), schedule("other")])
    window.schedule_table.setCurrentCell(0, 0)
    window.display_schedules([schedule("other"), schedule("selected")])
    monkeypatch.setattr(window, "work", lambda fn, done: fn())
    window.change_schedule(enabled=False)
    window.client.call.assert_called_once_with("schedule.change", id="selected", enabled=False, delete=False)
    window.display_schedules([schedule("other")])
    assert window.schedule_table.currentRow() == -1
    window.close()


def test_history_selection_follows_job_identity_when_new_row_arrives():
    app = QApplication.instance() or QApplication([])
    window = Console()
    def job(identity, time):
        return {"id": identity, "created_at": time, "kind": "backup", "status": "running", "done": 0, "total": 1}
    window.set_jobs([job("old", "2026-10-09T01:00:00")])
    window.jobs_table.setCurrentCell(0, 0)
    window.backup_table.setCurrentCell(0, 0)
    window.set_jobs([job("new", "2026-10-09T02:00:00")])
    assert window.jobs[window.jobs_table.currentRow()]["id"] == "old"
    assert window.backup_jobs[window.backup_table.currentRow()]["id"] == "old"
    window.disconnect_server()
    assert window.jobs_table.currentRow() == window.backup_table.currentRow() == -1
    window.close()


@pytest.mark.parametrize("reconnect", [False, True])
def test_connection_change_clears_previous_account_patch_and_schedule_views(monkeypatch, reconnect):
    app = QApplication.instance() or QApplication([])
    window = Console()
    window.account_table.setRowCount(1)
    window.patch_table.setRowCount(1)
    window.patch_output.setPlainText("Previous server output")
    window.patch_plan_id = "old-plan"
    window.patch_apply.setEnabled(True)
    window.schedules = [{"id": "old-schedule"}]
    window.schedule_table.setRowCount(1)
    window.connection_results = [{"hostname": "old-host"}]
    window.jobs = [{"id": "old-job"}]
    window.job_history = {"old-job": {"id": "old-job"}}
    window.backup_history = {"old-backup": {"id": "old-backup"}}
    window.resource_table.setRowCount(1)
    window.resource_loaded_job = "old-resource"
    if reconnect:
        monkeypatch.setattr(window, "reload", lambda: None)
        client = Mock()
        client.settings.host = "localhost"; client.settings.port = 7443
        window.attach_client(client, {"data_directory": "/opt/new/DATA"})
    else:
        window.disconnect_server()
    assert window.account_table.rowCount() == window.patch_table.rowCount() == window.schedule_table.rowCount() == 0
    assert not window.patch_output.toPlainText() and not window.schedules
    assert window.patch_plan_id is None and not window.patch_apply.isEnabled()
    assert not window.connection_results and not window.jobs and not window.job_history and not window.backup_history
    assert window.resource_table.rowCount() == window.backup_table.rowCount() == window.jobs_table.rowCount() == 0
    assert window.resource_loaded_job is None and not window.servers
    window.close()


def test_old_connection_failure_cannot_clear_new_poll(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Console()
    from PySide6.QtCore import QThreadPool
    pending = []
    monkeypatch.setattr(QThreadPool, "start", lambda pool, worker: pending.append(worker))
    window.work(lambda: None, lambda result: None, quiet=True)
    window.epoch += 1
    window.poll_busy = True
    window.status_line.setText("New connection polling")
    pending[0].signals.error.emit("Old connection lost")
    assert window.poll_busy
    assert window.status_line.text() == "New connection polling"
    assert not window.workers
    window.close()


@pytest.mark.parametrize("kind", ["connections", "accounts", "patches", "monitoring"])
def test_result_read_failure_retries_without_resubmitting_job(monkeypatch, kind):
    app = QApplication.instance() or QApplication([])
    window = Console()
    window.client = Mock()
    window.active_job = "saved-job"
    job = {"id": "saved-job", "kind": kind, "created_at": "2026-10-09T15:00:00+09:00",
           "status": "completed", "done": 1, "total": 1}
    requests = []
    monkeypatch.setattr(window, "work", lambda fn, done, **options: requests.append(options))
    window.set_jobs([job])
    assert len(requests) == 1
    requests[0]["on_error"]()
    window.set_jobs([job])
    assert len(requests) == 2
    window.client.call.assert_not_called()
    window.close()


def test_connection_warnings_visible_and_incomplete_not_counted_as_empty():
    app = QApplication.instance() or QApplication([])
    window = Console()
    window.display_connections([{"hostname": "lab", "ip": "127.0.0.1", "os": "Linux", "status": "completed",
                                "result": {"connections": [], "truncated": True}},
                               {"hostname": "warning-lab", "ip": "127.0.0.2", "os": "Linux", "status": "completed",
                                "result": {"connections": [], "warning": "Collection diagnostic"}}])
    assert "1 servers with no connections" in window.status_line.text()
    assert "1 servers reported collection warnings" in window.status_line.text()
    assert any(item.toolTip() == "Collection diagnostic" for item in window.graph.scene().items())
    window.close()


def test_recovery_details_prevent_desktop_job_submission(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Console()
    monkeypatch.setattr(window, "reload", lambda: None)
    client = Mock()
    client.settings.host = "localhost"; client.settings.port = 7443
    window.attach_client(client, {"data_directory": "/opt/sm/DATA", "history_errors": [
        {"file": "damaged.json.enc", "error": "InvalidToken"}]})
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append(text))
    window.start_job("backup")
    assert "damaged.json.enc: InvalidToken" in messages[0]
    client.call.assert_not_called()
    window.navigate(1)
    assert "history recovery required" in window.subtitle.text()
    assert "damaged.json.enc" in window.subtitle.toolTip()
    window.disconnect_server()
    assert not window.history_errors and not window.subtitle.toolTip()
    window.close()


def test_inventory_profile_selection_preserves_unconfigured_name(monkeypatch):
    app = QApplication.instance() or QApplication([])
    dialog = InventoryDialog(None, [{"hostname": "lab", "ip": "127.0.0.1", "os": "RHEL 9", "profile": "old-profile"}], ["rhel-admin", "default"])
    assert dialog.rows()[0]["profile"] == "old-profile"
    selector = dialog.grid.cellWidget(0, 3)
    assert "not configured" in selector.currentText()
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append(text))
    dialog.accept()
    assert "rows: 1" in messages[0] and dialog.result() == 0
    selector.setCurrentIndex(selector.findData("rhel-admin"))
    assert dialog.rows()[0]["profile"] == "rhel-admin"
    dialog.add_server()
    assert dialog.rows()[1]["profile"] == "default"
    dialog.close()


def test_connection_map_distinguishes_empty_and_cancelled_targets():
    app = QApplication.instance() or QApplication([])
    graph = ConnectionMap()
    graph.set_results([
        {"hostname": "empty-lab", "ip": "127.0.0.1", "os": "Linux", "status": "completed", "result": {"connections": []}},
        {"hostname": "cancelled-lab", "ip": "127.0.0.2", "os": "Linux", "status": "cancelled"},
    ])
    labels = [item.text() for item in graph.scene().items() if hasattr(item, "text")]
    assert "empty-lab" in labels and "cancelled-lab" in labels
    assert "No established connections" in labels and "Collection cancelled" in labels
    graph.close()


@pytest.mark.parametrize("query", ["127.0.0.1", "10.0.0.1", "22", " LAB "])
def test_map_search_includes_server_and_local_endpoint(query):
    app = QApplication.instance() or QApplication([])
    graph = ConnectionMap()
    graph.set_results([{"hostname": "lab", "ip": "127.0.0.1", "os": "Linux", "status": "completed", "result": {
        "connections": [{"local": {"address": "10.0.0.1", "port": "22"}, "remote": {"address": "192.0.2.1", "port": "51234"}}]}}], query)
    labels = [item.text() for item in graph.scene().items() if hasattr(item, "text")]
    assert "192.0.2.1" in labels and "No established connections" not in labels
    graph.close()


def test_connection_map_marks_capture_limit():
    app = QApplication.instance() or QApplication([])
    graph = ConnectionMap()
    graph.set_results([{"hostname": "lab", "ip": "127.0.0.1", "os": "Linux", "status": "completed",
                        "result": {"connections": [], "truncated": True}}])
    labels = [item.text() for item in graph.scene().items() if hasattr(item, "text")]
    assert "Capture limit reached: incomplete snapshot" in labels
    assert "Successful snapshot / 0 TCP peers" not in labels
    graph.close()


def test_activity_history_survives_recent_poll_and_updates_existing_status():
    app = QApplication.instance() or QApplication([])
    window = Console()
    def job(identity, status):
        return {"id": identity, "created_at": "2026-10-09T01:00:00", "kind": "connections", "status": status, "done": 1, "total": 1}
    window.set_jobs([job("old", "running")])
    window.set_jobs([job("new", "completed"), job("old", "completed")])
    window.set_jobs([job("new", "completed")])
    assert len(window.jobs) == 2 and window.job_history["old"]["status"] == "completed"
    window.disconnect_server()
    assert not window.job_history and not window.jobs
    window.close()


def test_duplicate_click_waits_for_submission_acknowledgement(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Console(); window.client = Mock()
    monkeypatch.setattr(window, "checked_hosts", lambda: ["lab"])
    requests = []
    monkeypatch.setattr(window, "work", lambda fn, done, **kwargs: requests.append((done, kwargs)))
    window.start_job("backup"); window.start_job("backup")
    assert len(requests) == 1 and window.submission_pending
    requests[0][1]["on_error"]()
    window.start_job("backup")
    assert len(requests) == 2
    window.disconnect_server()
    assert not window.submission_pending
    window.close()

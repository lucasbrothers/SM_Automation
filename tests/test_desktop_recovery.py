from unittest.mock import Mock
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox
from desktop.main import Console, InventoryDialog
from desktop.graph import ConnectionMap


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

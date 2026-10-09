from unittest.mock import Mock
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox
from desktop.main import Console, InventoryDialog


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

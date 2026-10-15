"""Windows agent administration renders lifecycle states and refreshes inventory."""
from unittest.mock import Mock
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from desktop.main import Console
from desktop.agent_setup import AgentDialog
from desktop.tables import row_identity


def test_agent_lifecycle_dialog_renders_and_removes_selected_identity(monkeypatch):
    app=QApplication.instance() or QApplication([]);window=Console();window.client=Mock()
    def call(method,**params):
        if method=='agent.list':return [{'id':'a'*32,'hostname':'z-host','status':'offline','last_seen':'2026-10-15','peer_ip':'127.0.0.1','version':'1','registered_at':'2026-10-15'}, {'id':'b'*32,'hostname':'a-host','status':'uninstalled','last_seen':'2026-10-15','peer_ip':'127.0.0.1','version':'1','registered_at':'2026-10-15'}]
        if method=='agent.policy.get':return {'enabled':False}
        return {}
    window.client.call.side_effect=call
    monkeypatch.setattr(window,'work',lambda fn,done,**kwargs:done(fn()))
    monkeypatch.setattr(window,'refresh_agent_inventory',lambda:None)
    dialog=AgentDialog(window)
    assert dialog.table.rowCount()==2
    dialog.table.sortItems(0,Qt.SortOrder.AscendingOrder);dialog.table.selectRow(0)
    assert dialog.table.item(0,1).text()=='제거됨'
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    dialog.revoke(True)
    assert any(call.args==('agent.revoke',) and call.kwargs=={'id':'b'*32,'remove':True} for call in window.client.call.call_args_list)
    dialog.close();window.client=None;window.close()

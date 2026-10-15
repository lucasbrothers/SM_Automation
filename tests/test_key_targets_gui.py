import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import Qt
from desktop.key_targets import PublicKeyTargetsDialog
from desktop.tables import row_identity
from desktop.main import Console

SERVERS=[{"hostname":"z","ip":"192.0.2.1","os":"Ubuntu"},{"hostname":"a","ip":"192.0.2.2","os":"AIX"},{"hostname":"win","ip":"192.0.2.3","os":"Windows","transport":"agent"}]

def test_picker_starts_empty_and_only_checks_requested_ssh_targets():
    app=QApplication.instance() or QApplication([])
    d=PublicKeyTargetsDialog(None,SERVERS,["z","win"])
    assert d.selected_hosts()==[] and not d.run_button.isEnabled()
    d.table.sortItems(1,Qt.SortOrder.AscendingOrder);d.select({"z","win"})
    assert d.selected_hosts()==["z"] and d.run_button.isEnabled()
    d.select(set());assert not d.run_button.isEnabled();d.close()

def test_deployment_passes_explicit_subset_not_equipment_book(monkeypatch):
    app=QApplication.instance() or QApplication([]);w=Console();w.servers=SERVERS
    monkeypatch.setattr(w,"require_client",lambda:True);monkeypatch.setattr(w,"checked_hosts",lambda:["z","a"])
    monkeypatch.setattr(PublicKeyTargetsDialog,"exec",lambda d:QDialog.DialogCode.Accepted)
    monkeypatch.setattr(PublicKeyTargetsDialog,"selected_hosts",lambda d:["a"])
    called=[];monkeypatch.setattr(w,"start_job",lambda *a,**k:called.append((a,k)))
    w.deploy_server_key();assert called==[(("deploy_key",),{"hosts_override":["a"]})];w.close()

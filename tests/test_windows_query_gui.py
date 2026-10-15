import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from desktop.main import Console

def test_windows_controls_and_result_columns(monkeypatch):
    app=QApplication.instance() or QApplication([])
    w=Console()
    w.servers=[{"hostname":"win","os":"Microsoft Windows 11"},{"hostname":"linux","os":"Ubuntu"}]
    monkeypatch.setattr(w,"checked_hosts",lambda:["win"])
    w.account_action.setCurrentIndex(1);w.update_windows_query_controls()
    assert not w.account_run_button.isEnabled() and not w.patch_plan_button.isEnabled()
    w.account_action.setCurrentIndex(0)
    assert w.account_run_button.isEnabled()
    w.display_accounts([{"hostname":"win","status":"completed","result":{"accounts":[{"username":"sample","uid":"S-1-5","enabled":False,"gid":"Users"}]}}])
    assert w.account_table.columnCount()==12 and w.account_table.rowCount()==1
    assert w.account_table.item(0,8).text()=="False"
    w.display_patches([{"hostname":"win","status":"completed","result":{"packages":[{"name":"KB123","installed":"2026-10-15","candidate":"Installed","description":"Security Update"}]}}],{"options":{"action":"list"}})
    assert w.patch_table.item(0,4).text()=="Security Update"
    monkeypatch.setattr(w,"checked_hosts",lambda:["linux"])
    w.account_action.setCurrentIndex(1);w.update_windows_query_controls()
    assert w.account_run_button.isEnabled() and w.patch_plan_button.isEnabled()
    w.close()

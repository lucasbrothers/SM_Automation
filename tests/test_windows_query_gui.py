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
    assert w.account_table.columnCount()==13 and w.account_table.rowCount()==1
    assert w.account_table.item(0,8).text()=="False"
    w.display_patches([{"hostname":"win","status":"completed","result":{"packages":[{"name":"KB123","installed":"2026-10-15","candidate":"Installed","description":"Security Update"}]}}],{"options":{"action":"list"}})
    assert w.patch_table.item(0,4).text()=="Security Update"
    monkeypatch.setattr(w,"checked_hosts",lambda:["linux"])
    w.account_action.setCurrentIndex(1);w.update_windows_query_controls()
    assert w.account_run_button.isEnabled() and w.patch_plan_button.isEnabled()
    w.close()


def test_aix_query_only_controls_and_resources(monkeypatch):
    app=QApplication.instance() or QApplication([]);w=Console()
    w.servers=[{"hostname":"aix","os":"AIX 7.2"}]
    monkeypatch.setattr(w,"checked_hosts",lambda:["aix"])
    w.account_action.setCurrentIndex(1);w.update_windows_query_controls()
    assert not w.account_run_button.isEnabled() and not w.patch_plan_button.isEnabled()
    w.account_action.setCurrentIndex(0);assert w.account_run_button.isEnabled()
    w.display_accounts([{"hostname":"aix","status":"completed","result":{"accounts":[{"username":"svc","uid":"200","gid":"staff","groups":"staff,system","enabled":False}]}}])
    assert w.account_table.item(0,12).text()=="staff,system"
    w.display_resources([{"hostname":"aix","status":"completed","result":{"load_average":[.1,.2,.3],"uptime":"3 days","memory_mb":{"used":512,"total":1024},"root_filesystem":{"capacity":"40%"}}}])
    assert w.resource_table.rowCount()==1 and w.resource_table.item(0,1).text()=="0.10 / 0.20 / 0.30"
    w.close()


def test_windows_resource_cpu_is_not_load_and_sorted_bars_stay_with_host():
    from PySide6.QtCore import Qt
    app=QApplication.instance() or QApplication([]);w=Console()
    w.resource_table.sortItems(0,Qt.SortOrder.AscendingOrder)
    def row(host,cpu,used,capacity):
        return {"hostname":host,"status":"completed","result":{"cpu_percent":cpu,"load_average":[],"uptime":"25시간 01분 01초","memory_mb":{"total":100,"used":used},"root_filesystem":{"capacity":str(capacity)+"%"}}}
    w.display_resources([row("z-win",15,90,80),row("a-win",25,20,30)])
    assert w.resource_table.item(0,0).text()=="a-win"
    assert w.resource_table.item(0,1).text()=="CPU 25.0%"
    assert w.resource_table.cellWidget(0,2).value()==20
    assert w.resource_table.cellWidget(1,2).value()==90
    w.close()

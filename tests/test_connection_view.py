"""Large snapshots stay bounded on screen and complete in search/export."""
from unittest.mock import Mock
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QFileDialog
import csv
from desktop.main import Console
from desktop.connection_view import filter_snapshot,table_rows,table_page


def snapshot(hosts=1000, peers=26):
    return [{'hostname':f'host-{i:04}', 'ip':f'10.0.{i//250}.{i%250+1}', 'os':'Linux','status':'completed','result':{'connections':[
        {'local':{'address':f'10.0.{i//250}.{i%250+1}','port':'22'},'remote':{'address':f'192.0.2.{j+1}','port':str(50000+j)}} for j in range(peers)]}} for i in range(hosts)]


def test_late_page_is_complete_and_search_includes_local_remote_and_host():
    rows=snapshot(11,26)
    assert table_page(rows,2)==list(table_rows(rows))[200:400]
    assert len(list(table_rows(rows)))==286
    assert len(filter_snapshot(rows,'HOST-0010'))==1
    assert len(list(table_rows(filter_snapshot(rows,'50025'))))==11
    assert len(list(table_rows(filter_snapshot(rows,'10.0.0.11:22'))))==26
    assert not filter_snapshot(rows,'not-present')


def test_thousand_hosts_render_only_current_page_and_keep_export_complete(monkeypatch,tmp_path):
    app=QApplication.instance() or QApplication([]);window=Console()
    rows=snapshot();window.connection_results=rows;window.update_map()
    assert window.map_page.maximum()==100
    assert window.connection_page.maximum()==130
    assert window.connection_table.rowCount()==200
    assert len(window.graph.scene().items())<2200
    assert window.graph.transform().m11()>=.5
    labels=lambda:[i.text() for i in window.graph.scene().items() if hasattr(i,'text')]
    assert 'host-0000' in labels() and 'host-0010' not in labels()
    window.map_page.setValue(100)
    assert 'host-0999' in labels() and 'host-0000' not in labels()
    assert len(list(table_rows(window.filtered_connections)))==26000
    path=tmp_path/"connections.csv"
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(path),"CSV"))
    window.export_widgets(window.connection_table.parentWidget())
    with path.open(encoding="utf-8-sig",newline="") as stream: exported=list(csv.reader(stream))
    assert len(exported)==26001
    assert exported[-1][1]=="host-0999"
    pending=[]
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:pending.append((fn,done)))
    window.peer_search.setText('host-0999');window.update_map()
    window.peer_search.setText('host-0001');window.update_map()
    pending[1][1](pending[1][0]());pending[0][1](pending[0][0]())
    assert [r['hostname'] for r in window.filtered_connections]==['host-0001']
    window.peer_search.setText('');window.update_map()
    assert len(window.filtered_connections)==1000
    window.close()


def test_checkbox_only_switches_saved_results_and_displays_observation_time(monkeypatch):
    from PySide6.QtCore import Qt
    app=QApplication.instance() or QApplication([]);window=Console()
    rows=snapshot(2,1)
    for row in rows:row['observed_at']='2026-10-15T01:23:45+00:00'
    window.remember_connections(rows)
    window.set_inventory([{k:r[k] for k in ('hostname','ip','os')} for r in rows]+[{'hostname':'new-host','ip':'192.0.2.99','os':'Linux'}])
    window.client=Mock()
    window.check_all(False)
    assert window.connection_results==[]
    for r in range(window.target_table.rowCount()):
        if window.target_table.item(r,0).data(Qt.ItemDataRole.UserRole)=='host-0001':window.target_table.item(r,0).setCheckState(Qt.CheckState.Checked)
    assert [r['hostname'] for r in window.connection_results]==['host-0001']
    assert '2026-10-15' in window.connection_table.item(0,4).text()
    assert any('2026-10-15' in i.text() for i in window.graph.scene().items() if hasattr(i,'text'))
    window.client.call.assert_not_called()
    window.close()

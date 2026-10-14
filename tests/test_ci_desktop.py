from unittest.mock import Mock
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QItemSelectionModel
from desktop.main import Console
from desktop.ci import safe_csv


def test_ci_page_renders_unknown_failed_stale_and_collects_selected(monkeypatch):
    app=QApplication.instance() or QApplication([])
    window=Console();window.client=Mock();window.user_role='admin'
    data={'rows':[{'hostname':'lab','ip':'127.0.0.2','stale':True,'collection_status':'failed','observed':{'cpu_model':'Xeon','allocated_cpus':2},'manual':{'customer':'Acme','operational_status':'운영'}}], 'total':1,'counts':{'운영':1,'유휴':0,'폐기':0,'미지정':0}}
    window.client.call.return_value=data
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:done(fn()))
    window.navigate(9)
    dashboard=window.ci_dashboard
    assert window.pages.currentWidget()==dashboard and dashboard.table.item(0,0).text()=='lab'
    assert dashboard.table.item(0,3).text()=='Acme'
    assert '재수집' in dashboard.table.item(0,17).text()
    dashboard.table.selectRow(0)
    called=[];monkeypatch.setattr(window,'start_job',lambda *args,**kw:called.append((args,kw)))
    dashboard.collect()
    assert called==[(('ci_inventory',),{'hosts_override':['lab']})]
    window.user_role='viewer';dashboard.refresh()
    assert not dashboard.edit_button.isEnabled() and not dashboard.bulk_button.isEnabled()
    assert not dashboard.collect_button.isEnabled()
    window.clear_session_views();assert dashboard.table.rowCount()==0
    window.client=None;window.close()


def test_csv_formula_and_numeric_values():
    assert safe_csv('=cmd')=="'=cmd"
    assert safe_csv(' @SUM(1)')=="' @SUM(1)"
    assert safe_csv(32)=='32' and safe_csv(None)==''

def test_ci_export_includes_every_filtered_page_and_all_attributes(tmp_path,monkeypatch):
    import zipfile
    from PySide6.QtWidgets import QFileDialog
    app=QApplication.instance() or QApplication([])
    window=Console();window.client=Mock()
    rows=[{'hostname':'h1','ip':'10.0.0.1','manual':{'customer':'Acme','notes':'=not-a-formula'},'observed':{'serial_number':'SN-1','allocated_cpus':2}},
          {'hostname':'h2','ip':'10.0.0.2','manual':{'owner':'Team'},'observed':{'serial_number':'SN-2'}}]
    def call(method,**params):
        return {'rows':[rows[params['offset']]],'total':2}
    window.client.call.side_effect=call
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:done(fn()))
    path=tmp_path/'assets.xlsx'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**kw:(str(path),'Excel (*.xlsx)'))
    window.ci_dashboard.export()
    with zipfile.ZipFile(path) as book:
        sheet=book.read('xl/worksheets/sheet1.xml').decode()
        assert 'SN-1' in sheet and 'SN-2' in sheet and 'Acme' in sheet and '=not-a-formula' in sheet
        assert '<f>' not in sheet and 'Serial number' in sheet
    assert [call.kwargs['offset'] for call in window.client.call.call_args_list]==[0,1]
    window.client=None;window.close()

@pytest.mark.parametrize('seconds,expected',[(0,'00:00:00'),(59,'00:00:59'),(60,'00:01:00'),(3661.9,'01:01:01'),(90061,'25:01:01'),(360000,'100:00:00'),('7201','02:00:01'),(None,None),('',None),(-1,None),(float('nan'),None),(float('inf'),None),(True,None)])
def test_uptime_uses_elapsed_hours_without_day_wrap(seconds,expected):
    from shared.ci_schema import display_value
    assert display_value('uptime_seconds',seconds)==expected
    assert display_value('allocated_cpus',16)==16


def test_ci_uptime_display_and_export_use_hours_minutes_seconds(tmp_path,monkeypatch):
    import csv
    from PySide6.QtWidgets import QFileDialog
    from desktop.ci import COLUMNS
    app=QApplication.instance() or QApplication([])
    window=Console();window.client=Mock()
    window.client.call.return_value={'rows':[{'hostname':'lab','ip':'127.0.0.1','observed':{'uptime_seconds':90061}}], 'total':1,'counts':{'운영':0,'유휴':0,'폐기':0,'미지정':1}}
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:done(fn()))
    window.ci_dashboard.refresh()
    column=next(i for i,(key,_) in enumerate(COLUMNS) if key=='uptime_seconds')
    assert window.ci_dashboard.table.item(0,column).text()=='25:01:01'
    path=tmp_path/'ci.csv'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**kw:(str(path),'CSV (*.csv)'))
    window.ci_dashboard.export()
    with path.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert rows[0]['Uptime (시간:분:초)']=='25:01:01'
    window.client=None;window.close()

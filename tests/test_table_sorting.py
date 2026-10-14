import pytest
from unittest.mock import Mock
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from desktop.main import Console, table, fill_identity_table, fill_table
from desktop.tables import row_identity
from desktop.backup_compare import ComparisonDialog
from desktop.ci import COLUMNS
from shared.ci_schema import FIELDS,AUTO_FIELDS


def app():
    return QApplication.instance() or QApplication([])


def test_numeric_and_ip_sort_preserve_entire_rows_and_refresh_order():
    application=app();grid=table(['Name','CPU','IP'])
    rows=[['h10',100,'10.0.0.100'],['h2',2,'10.0.0.2'],['h3',16,'10.0.0.10']]
    fill_table(grid,rows);grid.sortItems(1,Qt.SortOrder.AscendingOrder)
    assert [grid.item(i,0).text() for i in range(3)]==['h2','h3','h10']
    fill_table(grid,list(reversed(rows)))
    assert [grid.item(i,2).text() for i in range(3)]==['10.0.0.2','10.0.0.10','10.0.0.100']
    grid.sortItems(2,Qt.SortOrder.DescendingOrder)
    assert [grid.item(i,1).text() for i in range(3)]==['100','16','2']


def test_sorted_history_actions_use_identity_not_original_row(monkeypatch):
    application=app();window=Console();window.client=Mock()
    jobs=[{'id':'first','created_at':'2026-01-01','status':'completed','done':1,'total':1},
          {'id':'second','created_at':'2026-02-01','status':'completed','done':1,'total':1}]
    window.backup_jobs=jobs
    fill_identity_table(window.backup_table,jobs,[[j['created_at'],j['status'],'1/1',j['id']] for j in jobs])
    window.backup_table.sortItems(0,Qt.SortOrder.DescendingOrder);window.backup_table.selectRow(0)
    called=[];monkeypatch.setattr(window,'start_job',lambda *a,**kw:called.append(kw))
    window.compare_backup();assert called[0]['options']['baseline_job_id']=='second'
    window.jobs=jobs
    fill_identity_table(window.jobs_table,jobs,[[j['created_at'],'backup',j['status'],'1/1',j['id']] for j in jobs])
    window.jobs_table.sortItems(0,Qt.SortOrder.DescendingOrder);window.jobs_table.selectRow(0)
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:fn())
    window.cancel_selected_job();window.client.call.assert_called_with('job.cancel',id='second')
    window.client=None;window.close()


def test_comparison_sort_keeps_selected_diff_attached():
    application=app()
    rows=[{'hostname':'h','status':'completed','result':{'files':[
        {'path':'/z','status':'changed','before_size':100,'after_size':200,'diff':'Z diff'},
        {'path':'/a','status':'changed','before_size':2,'after_size':16,'diff':'A diff'}]}}]
    # report() also supports export, but this test targets the selection-to-diff binding.
    for item in rows[0]['result']['files']:
        item.update(before_sha256='a',after_sha256='b')
    dialog=ComparisonDialog(rows,{'id':'job'})
    dialog.files.sortItems(1,Qt.SortOrder.AscendingOrder);dialog.files.selectRow(0);dialog.detail()
    assert dialog.text.toPlainText()=='A diff'
    dialog.files.sortItems(3,Qt.SortOrder.DescendingOrder);dialog.files.selectRow(0);dialog.detail()
    assert dialog.text.toPlainText()=='Z diff'
    dialog.close()


def test_ci_all_attributes_horizontal_scroll_and_server_sort(monkeypatch):
    application=app();window=Console();window.client=Mock();dashboard=window.ci_dashboard
    window.client.call.return_value={'rows':[],'total':0,'counts':{'운영':0,'유휴':0,'폐기':0,'미지정':0}}
    monkeypatch.setattr(window,'work',lambda fn,done,**kw:done(fn()))
    assert set(FIELDS)|set(AUTO_FIELDS) <= {key for key,_ in COLUMNS}
    assert not dashboard.table.wordWrap()
    assert dashboard.table.horizontalScrollBarPolicy()==Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    column=next(i for i,(key,_) in enumerate(COLUMNS) if key=='allocated_cpus')
    dashboard.offset=100;dashboard.sort_column(column)
    assert window.client.call.call_args.kwargs['sort_key']=='allocated_cpus'
    assert not window.client.call.call_args.kwargs['descending'] and dashboard.offset==0
    dashboard.sort_column(column);assert window.client.call.call_args.kwargs['descending']
    window.client=None;window.close()


def test_auto_fit_reacts_to_window_size_and_manual_override():
    application=app();window=Console();window.show();application.processEvents()
    window.resize(1000,600);application.processEvents();window.fit_window()
    small=window.zoom_control.value();assert 60<=small<90
    assert window.sidebar_scroll.widgetResizable()
    for item in window.nav_buttons:
        assert item.minimumHeight()>=item.fontMetrics().lineSpacing()
    window.resize(1600,1100);application.processEvents();window.fit_window()
    assert window.zoom_control.value()>=small
    window.zoom_control.setValue(110);assert not window.auto_fit.isChecked()
    window.resize(1000,600);window.fit_window();assert window.zoom_control.value()==110
    window.auto_fit.setChecked(True);assert window.zoom_control.value()<110
    window.close()

def test_ci_horizontal_scroll_is_reachable_without_scrolling_inactive_forms():
    application=app();window=Console();window.navigate(9);window.show();window.resize(1000,650)
    application.processEvents();window.fit_window();application.processEvents()
    scrollbar=window.ci_dashboard.table.horizontalScrollBar()
    assert scrollbar.mapTo(window,scrollbar.rect().bottomRight()).y()<window.height()
    assert window.workspace_scroll.verticalScrollBar().maximum()==0
    window.close()

def test_sorted_target_lists_keep_checkboxes_and_ip_identity():
    application=app();window=Console()
    hosts=[{'hostname':'z-host','ip':'127.0.0.2','os':'Linux'}, {'hostname':'a-host','ip':'127.0.0.1','os':'Linux'}]
    window.set_inventory(hosts);window.target_table.sortItems(1,Qt.SortOrder.AscendingOrder)
    window.check_all(False)
    window.account_targets.sortItems(1,Qt.SortOrder.DescendingOrder)
    assert window.account_targets.item(0,1).text()=='z-host'
    window.account_targets.item(0,0).setCheckState(Qt.CheckState.Checked)
    assert window.checked_hosts()==['z-host']
    window.set_inventory(list(reversed(hosts)))
    assert window.checked_hosts()==['z-host']
    window.filter_servers('127.0.0.2')
    for row in range(window.target_table.rowCount()):
        assert window.target_table.isRowHidden(row)==(row_identity(window.target_table,row)!='z-host')
    window.close()

def test_scrollbars_stay_light_with_dark_os_palette():
    from PySide6.QtGui import QPalette,QColor
    application=app();original=application.palette();dark=QPalette(original)
    for role in (QPalette.ColorRole.Window,QPalette.ColorRole.Base,QPalette.ColorRole.Button):
        dark.setColor(role,QColor('#080808'))
    application.setPalette(dark)
    window=None
    try:
        window=Console();window.navigate(9);window.show();window.resize(1000,650)
        application.processEvents();window.fit_window();application.processEvents()
        bar=window.ci_dashboard.table.horizontalScrollBar()
        bar.setValue(bar.maximum()//2);application.processEvents()
        assert bar.height()>=14
        image=bar.grab().toImage()
        colors=[image.pixelColor(x,image.height()//2) for x in range(2,image.width()-2)]
        assert all(min(c.red(),c.green(),c.blue())>60 for c in colors)
        assert any(c.red()>200 and c.blue()>200 for c in colors)  # Track is light.
        assert any(90<c.red()<180 and c.blue()>c.red() for c in colors)  # Handle stays distinct.
        check=window.auto_fit.grab().toImage()
        check_colors=[check.pixelColor(x,check.height()//2) for x in range(3,min(16,check.width()))]
        assert any(c.blue()>150 and c.blue()>c.red()+50 for c in check_colors)
        window.grab().save('logs/ci-light-scrollbars-preview.png')
    finally:
        if window:window.close()
        application.setPalette(original)

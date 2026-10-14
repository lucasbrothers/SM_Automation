import io
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from backup.compare import unpack,compare
from desktop.report_excel import write_report


def archive(files):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as handle:
        for name,content in files.items():
            item=tarfile.TarInfo(name);item.size=len(content);item.mode=0o600;handle.addfile(item,io.BytesIO(content))
    return output.getvalue()


def test_file_changes_and_sensitive_value_redaction():
    old=unpack(archive({'etc/a':b'one\n','etc/same':b'same','etc/removed':b'gone','etc/secret.conf':b'password=synthetic-old-secret\n','etc/key':b'-----BEGIN PRIVATE KEY-----\nsynthetic-old-key'}))
    new=unpack(archive({'etc/a':b'two\n','etc/same':b'same','etc/added':b'new','etc/secret.conf':b'password=synthetic-new-secret\n','etc/key':b'-----BEGIN PRIVATE KEY-----\nsynthetic-new-key'}))
    rows=compare(old,new);states={r['path']:r['status'] for r in rows}
    assert states['/etc/a']=='changed' and states['/etc/same']=='unchanged'
    assert states['/etc/removed']=='removed' and states['/etc/added']=='added'
    assert '-one' in next(r['diff'] for r in rows if r['path']=='/etc/a')
    assert 'synthetic-old-secret' not in str(rows) and 'synthetic-new-key' not in str(rows)


def test_excel_report_sheets_formulas_and_highlighting(tmp_path):
    path=tmp_path/'report.xlsx';write_report(path,[('요약',[['이름','상태'],['=1+1','변경']]),('차이',[['파일','내용'],['a','line1\nline2']])])
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():ET.fromstring(archive.read(name))
        xml=archive.read('xl/worksheets/sheet1.xml').decode()
        assert 't="inlineStr"' in xml and '=1+1' in xml and '<f>' not in xml
        assert 's="2"' in xml and 'frozen' in xml

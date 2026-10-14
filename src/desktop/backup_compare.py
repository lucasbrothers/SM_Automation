"""Equipment-book backup comparison overview and Excel report."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QPlainTextEdit,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox
from desktop.report_excel import write_report
LABELS={'changed':'변경','added':'추가','removed':'삭제','unchanged':'동일','failed':'실패'}


def report(rows,job):
    summary=[['장비록','기준 백업 ID','비교 ID','대상 수','완료','변경 장비','실패','변경 파일','미완료']]
    hosts=[['CLIENT','IP','결과','비교 파일','변경 파일','설명']];files=[['CLIENT','파일','변경 구분','백업 크기','현재 크기','백업 SHA256','현재 SHA256']];details=[['CLIENT','파일','변경 구분','변경 내용 (민감값 제외)']]
    success=changed=failed=count=0
    for row in rows:
        result=row.get('result',{});ok=row['status']=='completed';success+=ok;failed+=not ok
        changed+=bool(ok and result.get('changed'));count+=result.get('changed',0) if ok else 0
        hosts.append([row['hostname'],row.get('ip',''),('변경 있음' if result.get('changed') else '동일') if ok else '실패',result.get('total',0),result.get('changed',0),row.get('error',result.get('scope',''))])
        for item in result.get('files',[]):
            if item['status']=='unchanged':continue
            status=LABELS[item['status']];files.append([row['hostname'],item['path'],status,item['before_size'],item['after_size'],item['before_sha256'],item['after_sha256']]);details.append([row['hostname'],item['path'],status,item['diff']])
    summary.append([job.get('equipment_book_name') or '개별 선택',job.get('options',{}).get('baseline_job_id',''),job.get('id',''),job.get('total',len(rows)),success,changed,failed,count,max(0,job.get('total',len(rows))-len(rows))])
    return [('장비록 요약',summary),('장비별 결과',hosts),('변경 파일',files),('상세 차이',details)]


class ComparisonDialog(QDialog):
    def __init__(self,rows,job,parent=None):
        super().__init__(parent);self.rows=rows;self.job=job;self.setWindowTitle('장비록 / 백업 설정 변경 비교');self.resize(1100,740)
        layout=QVBoxLayout(self);sheets=report(rows,job);summary=sheets[0][1][1]
        heading=QLabel(f'{summary[0]}  |  대상 {summary[3]}대  ·  변경 {summary[5]}대 / {summary[7]}파일  ·  실패 {summary[6]}대  ·  미완료 {summary[8]}대');heading.setWordWrap(True);heading.setStyleSheet('font-size:15pt;font-weight:700;color:#17365d');layout.addWidget(heading)
        note=QLabel('설정 파일 내용과 Unix 권한·소유자·링크 비교입니다. 시각/실시간 명령 출력은 제외하며, 실패 장비를 동일 상태로 판정하지 않습니다.');note.setWordWrap(True);layout.addWidget(note)
        self.hosts=QTableWidget();self.fill(self.hosts,sheets[1][1]);self.hosts.setMaximumHeight(180);layout.addWidget(self.hosts)
        actions=QHBoxLayout();self.only_changes=QCheckBox('변경 파일만 표시');self.only_changes.setChecked(True);self.only_changes.toggled.connect(self.load_host);actions.addWidget(self.only_changes)
        save=QPushButton('장비록 비교 엑셀 다운로드');save.clicked.connect(self.export);actions.addWidget(save);actions.addStretch();layout.addLayout(actions)
        self.files=QTableWidget();self.files.itemSelectionChanged.connect(self.detail);layout.addWidget(self.files,2)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);layout.addWidget(self.text,1)
        self.setStyleSheet('QTableWidget,QPlainTextEdit {background:white;color:#20354d;} QTableWidget::item:selected {background:#cfe2ff;color:#102a4c;}')
        self.hosts.itemSelectionChanged.connect(self.load_host)
        self.loaded_files={};self.request_number=0;self.closed=False
        self.finished.connect(lambda _:setattr(self,"closed",True))
        self.populate()
        if self.rows:self.hosts.setCurrentCell(0,0)

    def fetch(self,row,changes_only):
        if not row.get("result",{}).get("report_path"):return row.get("result",{}).get("files",[])
        result=[];offset=0
        while True:
            page=self.parent().client.call("backup.comparison",job_id=self.job["id"],hostname=row["hostname"],offset=offset,limit=100,changes_only=changes_only)
            result.extend(page["items"]);offset+=len(page["items"])
            if offset>=page["total"]:return result

    def load_host(self,*_):
        index=self.hosts.currentRow()
        if not 0<=index<len(self.rows):return
        self.request_number+=1;request=self.request_number
        row=self.rows[index];only=self.only_changes.isChecked();parent=self.parent()
        def loaded(items):
            if self.closed or request!=self.request_number:return
            self.loaded_files={row["hostname"]:items};self.populate()
        if parent and getattr(parent,"client",None) and row["status"]=="completed":
            parent.work(lambda:self.fetch(row,only),loaded)
        else:loaded(row.get("result",{}).get("files",[]))

    def fill(self,table,rows):
        table.setColumnCount(len(rows[0]));table.setHorizontalHeaderLabels(rows[0]);table.setRowCount(len(rows)-1);table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for r,row in enumerate(rows[1:]):
            for c,value in enumerate(row):
                item=QTableWidgetItem(str(value if value is not None else ''));table.setItem(r,c,item)
                if '실패' in row:item.setBackground(QColor('#fce4d6'))
        table.resizeColumnsToContents();table.horizontalHeader().setStretchLastSection(True)

    def populate(self,*_):
        self.items=[];values=[['CLIENT','파일 경로','상태','백업 크기','현재 크기']]
        for row in self.rows:
            for item in self.loaded_files.get(row['hostname'],[]):
                if self.only_changes.isChecked() and item['status']=='unchanged':continue
                self.items.append(item);values.append([row['hostname'],item['path'],LABELS[item['status']],item['before_size'],item['after_size']])
        self.fill(self.files,values)
        for index,item in enumerate(self.items):
            color={'added':'#e2f0d9','removed':'#fce4d6','changed':'#fff2cc'}.get(item['status'])
            if color:
                for col in range(self.files.columnCount()):self.files.item(index,col).setBackground(QColor(color))
        if self.items:self.files.setCurrentCell(0,0)
        else:self.text.setPlainText('변경 파일이 없습니다. 상단 실패 장비가 있는지도 확인하세요.')

    def detail(self):
        row=self.files.currentRow()
        if 0<=row<len(self.items):self.text.setPlainText(self.items[row]['diff'] or '변경 없음')

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'비교 결과 저장','backup-comparison.xlsx','Excel (*.xlsx)')
        if not path:return
        def export_work():
            import tempfile,json
            from pathlib import Path
            with tempfile.TemporaryDirectory(prefix="sm-comparison-export-") as temporary:
                files=Path(temporary)/"files.jsonl";details=Path(temporary)/"details.jsonl"
                sheets=report(self.rows,self.job)
                with files.open("w",encoding="utf-8") as file_stream,details.open("w",encoding="utf-8") as detail_stream:
                    file_stream.write(json.dumps(sheets[2][1][0],ensure_ascii=False)+"\n")
                    detail_stream.write(json.dumps(sheets[3][1][0],ensure_ascii=False)+"\n")
                    for row in self.rows:
                        copied={**row,"result":dict(row.get("result",{}))}
                        copied["result"]["files"]=self.fetch(row,True) if row["status"]=="completed" else []
                        partial=report([copied],self.job)
                        for entry in partial[2][1][1:]:file_stream.write(json.dumps(entry,ensure_ascii=False)+"\n")
                        for entry in partial[3][1][1:]:detail_stream.write(json.dumps(entry,ensure_ascii=False)+"\n")
                def records(source):
                    with source.open(encoding="utf-8") as stream:
                        for line in stream:yield json.loads(line)
                write_report(path,[sheets[0],sheets[1],("변경 파일",records(files)),("상세 차이",records(details))]);return path
        parent=self.parent()
        if parent and getattr(parent,"client",None):
            parent.work(export_work,lambda result:self.text.setPlainText("엑셀 저장 완료: "+result))
        else:
            try:export_work()
            except Exception as exc:QMessageBox.warning(self,"저장 실패",str(exc));return
            self.text.setPlainText("엑셀 저장 완료: "+path)

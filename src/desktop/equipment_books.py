"""Equipment book editor: named, overlapping selections of existing CLIENTs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,QListWidget,QListWidgetItem,QPushButton,QLabel,QMessageBox


class EquipmentBooks(QDialog):
    def __init__(self,client,servers,parent=None,readonly=False):
        super().__init__(parent);self.client=client;self.servers=servers;self.identity=None;self.chosen=None
        self.setWindowTitle('장비록 관리');self.resize(850,650)
        self.setStyleSheet('QListWidget, QLineEdit, QPlainTextEdit { background:white; color:#20354d; } QListWidget::item:selected { background:#cfe2ff; color:#102a4c; }')
        layout=QVBoxLayout(self);layout.addWidget(QLabel('장비는 여러 장비록에 포함할 수 있습니다. 구성 변경은 이후 작업에 적용됩니다.'))
        split=QHBoxLayout();self.books=QListWidget();self.books.currentRowChanged.connect(self.select);split.addWidget(self.books)
        right=QVBoxLayout();form=QFormLayout();self.name=QLineEdit();self.description=QLineEdit();form.addRow('장비록 이름',self.name);form.addRow('설명',self.description);right.addLayout(form)
        self.members=QListWidget()
        for server in servers:
            item=QListWidgetItem(server['hostname']+' · '+server['ip']);item.setData(Qt.ItemDataRole.UserRole,server['hostname']);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);self.members.addItem(item)
        right.addWidget(self.members);split.addLayout(right,2);layout.addLayout(split)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        actions=QHBoxLayout()
        for text,callback,write in [('새 장비록',self.new,True),('저장',self.save,True),('삭제',self.delete,True),('이 장비록을 실행 대상으로 선택',self.choose,False),('닫기',self.reject,False)]:
            button=QPushButton(text);button.clicked.connect(callback);button.setEnabled(not readonly or not write);actions.addWidget(button)
        layout.addLayout(actions);self.refresh()

    def refresh(self,identity=None):
        try:rows=self.client.call('equipment.book.list')
        except Exception as exc:self.status.setText(str(exc));return
        self.books.blockSignals(True);self.books.clear()
        for row in rows:
            item=QListWidgetItem(row['name']+' ('+str(len(row['hosts']))+')');item.setData(Qt.ItemDataRole.UserRole,row);self.books.addItem(item)
        self.books.blockSignals(False)
        for index,row in enumerate(rows):
            if row['id']==identity:self.books.setCurrentRow(index);return
        self.new()

    def new(self):
        self.identity=None;self.books.blockSignals(True);self.books.setCurrentRow(-1);self.books.clearSelection();self.books.blockSignals(False);self.name.clear();self.description.clear()
        for index in range(self.members.count()):self.members.item(index).setCheckState(Qt.CheckState.Unchecked)

    def select(self,index):
        if index<0:return
        row=self.books.item(index).data(Qt.ItemDataRole.UserRole);self.identity=row['id'];self.name.setText(row['name']);self.description.setText(row.get('description',''))
        known=set()
        for index in range(self.members.count()):
            item=self.members.item(index);host=item.data(Qt.ItemDataRole.UserRole);known.add(host);item.setCheckState(Qt.CheckState.Checked if host in row['hosts'] else Qt.CheckState.Unchecked)
        missing=set(row['hosts'])-known;self.status.setText('목록에서 제거된 장비: '+', '.join(sorted(missing)) if missing else '')

    def save(self):
        hosts=[self.members.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.members.count()) if self.members.item(i).checkState()==Qt.CheckState.Checked]
        try:row=self.client.call('equipment.book.save',id=self.identity,name=self.name.text(),description=self.description.text(),hosts=hosts)
        except Exception as exc:self.status.setText(str(exc));return
        self.refresh(row['id']);self.status.setText('장비록 저장 완료')

    def delete(self):
        if not self.identity:return
        try:self.client.call('equipment.book.delete',id=self.identity)
        except Exception as exc:self.status.setText(str(exc));return
        self.refresh();self.status.setText('장비록 삭제 완료')

    def choose(self):
        if not self.identity:return
        self.chosen=self.identity;self.accept()

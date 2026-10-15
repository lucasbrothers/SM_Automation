"""Explicit, independent CLIENT selection for SERVER public-key deployment."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QDialogButtonBox
from desktop.tables import enable_sorting,populate,row_identity

class PublicKeyTargetsDialog(QDialog):
    def __init__(self,parent,servers,current):
        super().__init__(parent);self.setWindowTitle("SERVER 공개키 배포 대상 선택");self.resize(780,540)
        body=QVBoxLayout(self)
        note=QLabel("체크한 장비의 CLIENT 접속 계정에만 배포합니다. 장비록·다른 화면의 선택은 바뀌지 않습니다.\n최초 호스트 키는 자동 등록하며, 기존 키가 바뀌면 연결을 차단합니다. 접속 계정/비밀번호 설정이 필요합니다.")
        note.setWordWrap(True);body.addWidget(note)
        self.current=set(current);self.servers={r["hostname"]:r for r in servers}
        actions=QHBoxLayout()
        for title,callback in [("현재 선택 가져오기",lambda:self.select(self.current)),("모두 해제",lambda:self.select(set()))]:
            button=QPushButton(title);button.clicked.connect(callback);actions.addWidget(button)
        actions.addStretch();body.addLayout(actions)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(["선택","장비","IP","OS","전송 방식"])
        enable_sorting(self.table)
        populate(self.table,[["",r["hostname"],r["ip"],r["os"],"에이전트 — 공개키 불필요" if r.get("transport")=="agent" else "SSH"] for r in servers],[r["hostname"] for r in servers])
        sorting=self.table.isSortingEnabled();self.table.setSortingEnabled(False)
        for index,r in enumerate(servers):
            item=self.table.item(index,0)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | (Qt.ItemFlag.ItemIsUserCheckable if r.get("transport")!="agent" else Qt.ItemFlag.NoItemFlags))
            item.setCheckState(Qt.CheckState.Unchecked)
        self.table.setSortingEnabled(sorting);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True);body.addWidget(self.table)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.run_button=buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);body.addWidget(buttons)
        self.table.itemChanged.connect(self.update_count);self.update_count()

    def selected_hosts(self):
        return [row_identity(self.table,r) for r in range(self.table.rowCount())
                if self.table.item(r,0).checkState()==Qt.CheckState.Checked and self.servers[row_identity(self.table,r)].get("transport")!="agent"]

    def select(self,hosts):
        for r in range(self.table.rowCount()):
            name=row_identity(self.table,r);eligible=self.servers[name].get("transport")!="agent"
            self.table.item(r,0).setCheckState(Qt.CheckState.Checked if name in hosts and eligible else Qt.CheckState.Unchecked)

    def update_count(self,*_):
        count=len(self.selected_hosts());self.run_button.setText(f"선택한 {count}대에 배포");self.run_button.setEnabled(count>0)

    def accept(self):
        if self.selected_hosts():super().accept()

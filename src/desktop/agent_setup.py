"""Administration UI for IP/port-only Windows setup and agent lifecycle."""
import hashlib
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,QSpinBox,QPushButton,QFileDialog,QMessageBox
from desktop.tables import enable_sorting,populate,row_identity
from PySide6.QtWidgets import QTableWidget
from desktop.theme import LIGHT_CONTROLS,light_palette

from datetime import datetime,timezone

STATUS={'online':'접속 중','offline':'오프라인','uninstalled':'제거됨','revoked':'접속 차단'}
DEFAULT_NETWORKS='127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, ::1/128, fc00::/7'


from shared.agent_installer import bind_installer

class AgentDialog(QDialog):
    def __init__(self,console):
        super().__init__(console);self.console=console;self.setWindowTitle('Windows CLIENT 설치 / 상태 관리');self.resize(1000,650)
        self.setPalette(light_palette());self.setStyleSheet(LIGHT_CONTROLS)
        layout=QVBoxLayout(self)
        note=QLabel('CLIENT는 설치 시 SERVER IP와 포트만 입력합니다. 설치 파일을 저장하면 아래 네트워크에서 신규 장비 자동 등록을 허용합니다. 장비는 CLIENT → SERVER TLS로 연결하며 SSH/CLIENT 인바운드 포트를 사용하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        fields=QHBoxLayout();self.networks=QLineEdit(DEFAULT_NETWORKS);self.networks.setPlaceholderText('등록 허용 출발지 CIDR, 쉼표 구분')
        self.hours=QSpinBox();self.hours.setRange(1,168);self.hours.setValue(24);self.hours.setSuffix(' 시간')
        self.limit=QSpinBox();self.limit.setRange(1,5000);self.limit.setValue(1000);self.limit.setSuffix(' 대')
        fields.addWidget(QLabel('신규 등록 허용 범위'));fields.addWidget(self.networks,1);fields.addWidget(self.hours);fields.addWidget(self.limit);layout.addLayout(fields)
        actions=QGridLayout()
        for index,(title,fn) in enumerate([('설치 파일 저장 / 등록 허용',self.export),('신규 등록 닫기',self.close_enrollment),('상태 새로고침',self.refresh),('선택 CLIENT 접속 차단',lambda:self.revoke(False)),('선택 CLIENT 목록에서 제거',lambda:self.revoke(True)),('상태 CSV 저장',lambda:self.console.export_widgets(self))]):
            b=QPushButton(title);b.clicked.connect(fn);actions.addWidget(b,index//3,index%3)
        layout.addLayout(actions)
        self.health=QLabel();self.health.setWordWrap(True);layout.addWidget(self.health)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['CLIENT','상태','최근 접속','접속 출발 IP','버전','최초 등록','장비 ID']);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);enable_sorting(self.table);layout.addWidget(self.table,1)
        footer=QLabel('120초 이상 접속이 없으면 오프라인입니다. 오프라인은 제거 확정이 아닙니다. 정상 제거 통보는 제거됨으로 표시합니다. 목록 제거 시 장비 인증을 폐기하며 CI/작업 이력은 보존합니다.');footer.setWordWrap(True);layout.addWidget(footer)
        support=QLabel('Windows agent 지원: CI · TCP 조회 · SYSTEM PowerShell 명령 · 일반 파일 전송(8 MiB). 백업·설정 비교(agent 1.1)는 지원하며 Linux 전용 계정·패치·보안 작업은 지원하지 않습니다.');support.setWordWrap(True);layout.addWidget(support)
        self.closed=False;self.busy=False;self.generation=0;self.policy_loaded=False;self.finished.connect(lambda _:setattr(self,'closed',True))
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(30000)
        self.refresh()

    def refresh(self,force=False):
        if self.closed or (self.busy and not force):return
        self.generation+=1;generation=self.generation
        self.busy=True;client=self.console.client
        def loaded(data):
            if self.closed or generation!=self.generation:return
            self.busy=False
            rows,policy=data
            if not self.policy_loaded:
                self.networks.setText(', '.join(policy.get('networks',DEFAULT_NETWORKS.split(', '))));self.limit.setValue(policy.get('max_new',1000));self.policy_loaded=True
            populate(self.table,[[r['hostname'],STATUS.get(r['status'],r['status']),r['last_seen'],r['peer_ip'],r['version'],r['registered_at'],r['id']] for r in rows],[r['id'] for r in rows]);self.table.resizeColumnsToContents()
            accepting=bool(policy.get('enabled') and policy.get('expires_at') and datetime.fromisoformat(policy['expires_at'])>datetime.now(timezone.utc) and policy.get('used',0)<policy.get('max_new',1000))
            self.health.setText(('신규 등록 허용' if accepting else '신규 등록 닫힘')+' · 만료: '+str(policy.get('expires_at') or '—')+' · 등록: '+str(policy.get('used',0))+'/'+str(policy.get('max_new',1000)))
        self.console.work(lambda:(client.call('agent.list'),client.call('agent.policy.get')),loaded,on_error=lambda:setattr(self,'busy',False))

    def parameters(self):return {'networks':[v.strip() for v in self.networks.text().split(',') if v.strip()],'hours':self.hours.value(),'max_new':self.limit.value()}

    def export(self):
        root=Path(__file__).resolve().parents[2]
        source=next((p for p in [root/'deploy/windows-client-base.exe',root/'release/windows-client-base.exe'] if p.exists()),None)
        if source is None:QMessageBox.warning(self,'설치 파일 없음','최신 GUI 설치 패키지의 Windows CLIENT 설치 파일이 필요합니다.');return
        path,_=QFileDialog.getSaveFileName(self,'Windows CLIENT 설치 파일 저장','SM-Windows-Client-Setup.exe','Windows installer (*.exe)')
        if not path:return
        client=self.console.client;params=self.parameters()
        def build():
            identity=client.call('agent.server_identity')
            result=bind_installer(source,path,identity['sha256'])
            client.call('agent.policy.save',enabled=True,**params)
            return result
        self.console.work(build,lambda result:(self.health.setText('설치 파일 저장 완료: '+result+' · CLIENT에서 IP와 포트만 입력하세요.'),self.refresh()))

    def close_enrollment(self):
        client=self.console.client;params=self.parameters()
        self.console.work(lambda:client.call('agent.policy.save',enabled=False,**params),lambda _:self.refresh())

    def revoke(self,remove):
        identity=row_identity(self.table)
        if not identity:return
        text='관리 목록에서 제거하고 장비 인증을 폐기할까요? CI/작업 이력은 보존합니다.' if remove else '이 CLIENT의 접속을 차단할까요?'
        if QMessageBox.question(self,'Windows CLIENT 관리',text)!=QMessageBox.StandardButton.Yes:return
        client=self.console.client
        self.console.work(lambda:client.call('agent.revoke',id=identity,remove=remove),lambda _:(self.refresh(True),self.console.refresh_agent_inventory()))

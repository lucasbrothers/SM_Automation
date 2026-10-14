"""CI dashboard: paged asset search, explicit discovery and bulk metadata edits."""
import csv
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QDialog, QFormLayout, QCheckBox, QDialogButtonBox, QScrollArea,
    QFileDialog, QMessageBox, QPlainTextEdit)
from shared.ci_schema import FIELDS, AUTO_FIELDS, display_value
from desktop.report_excel import write_report

COLUMNS = [("hostname", "Hostname"), ("ip", "관리 IP"), ("primary_ip", "대표 IP"),
    ("customer", "고객사"), ("operational_status", "운영상태"), ("service_name", "서비스명"),
    ("service_grade", "서비스 등급"), ("owner", "담당자"), ("os_name", "OS"), ("os_version", "버전"),
    ("hardware_model", "모델"), ("serial_number", "Serial"), ("cpu_model", "CPU 모델"),
    ("allocated_cpus", "할당 vCPU"), ("allocated_memory_gib", "할당 RAM GiB"), ("gpu", "GPU"),
    ("uptime_seconds", AUTO_FIELDS["uptime_seconds"]), ("collection_status", "수집 상태"), ("last_success", "최근 성공")]

# Keep familiar overview columns first, then expose every discovered/manual attribute.
COLUMNS += [(key, label) for key,label in {**AUTO_FIELDS, **FIELDS,
    "last_attempt":"최근 수집 시도", "error":"수집 오류", "updated_at":"자산 변경 시각",
    "observed_ip":"최근 수집 관리 IP", "stale":"주소 변경 여부", "os":"등록 OS", "profile":"SSH 프로필"}.items()
    if key not in {key for key,_ in COLUMNS}]


def flattened(row):
    return {**row.get("observed", {}), **row.get("manual", {}), **{k:v for k,v in row.items() if k not in {"observed", "manual"}}}


def value_text(value):
    if value is None or value == "":
        return "미수집"
    return str(value)


def safe_csv(value):
    text = "" if value is None else str(value)
    return "'"+text if text.lstrip().startswith(("=", "+", "-", "@")) else text


class CIDashboard(QWidget):
    def __init__(self, console):
        super().__init__()
        self.console = console
        self.rows = []
        self.offset = 0
        self.total = 0
        self.generation = 0
        self.sort_key = None; self.descending = False
        layout = QVBoxLayout(self)
        info = QLabel("CI 자산 관리 · 자동 수집은 선택한 CLIENT에 SSH로 접속합니다. 직접 입력한 정보는 재수집해도 유지됩니다.")
        info.setWordWrap(True); layout.addWidget(info)
        bar = QHBoxLayout()
        self.query = QLineEdit(); self.query.setPlaceholderText("Hostname / IP / 고객사 / 서비스명 / 자산 속성 검색")
        self.status = QComboBox(); self.status.addItems(["전체 상태", "운영", "유휴", "폐기"])
        self.scope = QComboBox(); self.scope.addItems(["전체 장비", "현재 장비록"])
        bar.addWidget(self.query, 1); bar.addWidget(self.status); bar.addWidget(self.scope)
        self.add_button(bar, "조회", lambda: self.refresh(True))
        self.query.returnPressed.connect(lambda: self.refresh(True))
        layout.addLayout(bar)
        self.metrics = QLabel("조회 전"); self.metrics.setWordWrap(True); layout.addWidget(self.metrics)
        actions = QHBoxLayout()
        self.collect_button = self.add_button(actions, "선택 / 장비록 정보 수집", self.collect)
        self.edit_button = self.add_button(actions, "선택 장비 개별 / 일괄 편집", self.edit)
        self.bulk_button = self.add_button(actions, "조회 전체 일괄 편집", self.edit_filtered)
        self.add_button(actions, "상세 보기", self.details)
        self.add_button(actions, "조회 전체 CSV / Excel 저장", self.export)
        actions.addStretch(); layout.addLayout(actions)
        self.table = QTableWidget(0, len(COLUMNS)); self.table.setHorizontalHeaderLabels([label for _,label in COLUMNS])
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_column)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(145)
        self.table.horizontalHeader().setMinimumSectionSize(110)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.itemDoubleClicked.connect(lambda _: self.details())
        layout.addWidget(self.table, 1)
        paging = QHBoxLayout()
        self.prev = self.add_button(paging, "이전 100", lambda: self.page(-100))
        self.next = self.add_button(paging, "다음 100", lambda: self.page(100))
        self.page_label = QLabel(); paging.addWidget(self.page_label); paging.addStretch(); layout.addLayout(paging)
        note = QLabel("미수집·미확인은 실제 값이 아닙니다. VM/컨테이너는 노출된 하드웨어·자원 기준이며 상세 화면에서 수집 제한을 확인하세요. Ctrl/Shift로 여러 행을 선택할 수 있습니다.")
        note.setWordWrap(True); layout.addWidget(note)

    def add_button(self, layout, title, fn):
        b = QPushButton(title); b.clicked.connect(fn); layout.addWidget(b); return b

    def clear(self):
        self.generation += 1; self.rows = []; self.table.setRowCount(0); self.metrics.setText("조회 전"); self.offset = 0; self.total = 0

    def filters(self):
        params = {"query": self.query.text().strip(), "operational_status": self.status.currentText() if self.status.currentIndex() else ""}
        if self.scope.currentIndex():
            book = self.console.active_book()
            params["hosts"] = book["hosts"] if book else []
        if self.sort_key:
            params.update(sort_key=self.sort_key, descending=self.descending)
        return params

    def refresh(self, reset=False):
        if not self.console.client:
            self.clear(); return
        if reset: self.offset = 0
        self.generation += 1; generation = self.generation
        client = self.console.client
        self.collect_button.setEnabled(getattr(self.console, "user_role", "admin") != "viewer")
        self.edit_button.setEnabled(getattr(self.console, "user_role", "admin") == "admin")
        self.bulk_button.setEnabled(self.edit_button.isEnabled())
        def loaded(data):
            if generation != self.generation: return
            self.rows = data["rows"]; self.total = data["total"]
            if self.offset >= self.total and self.offset:
                self.offset = max(0, ((self.total-1)//100)*100); self.refresh(); return
            self.table.setRowCount(len(self.rows))
            for i, row in enumerate(self.rows):
                flat = flattened(row)
                if row.get("stale"): flat["collection_status"] = "주소 변경 · 재수집 필요"
                elif row.get("collection_status") == "failed": flat["collection_status"] = "실패 · 상세 확인"
                elif row.get("observed", {}).get("warnings"): flat["collection_status"] = "완료 · 참고 있음"
                for j,(key,_) in enumerate(COLUMNS):
                    text = value_text(display_value(key, flat.get(key)))
                    item = QTableWidgetItem(text.replace("\r", "").replace("\n", " / "))
                    item.setToolTip(text)
                    if j == 0: item.setData(Qt.ItemDataRole.UserRole, row["hostname"])
                    self.table.setItem(i,j,item)
            self.table.resizeColumnsToContents()
            counts = data["counts"]
            self.metrics.setText(f"조회 {self.total}대  |  운영 {counts['운영']}  ·  유휴 {counts['유휴']}  ·  폐기 {counts['폐기']}  ·  미지정 {counts['미지정']}")
            self.page_label.setText(f"{self.offset+1 if self.total else 0}–{min(self.offset+100,self.total)} / {self.total}")
            self.prev.setEnabled(self.offset > 0); self.next.setEnabled(self.offset+100 < self.total)
        params = self.filters(); offset = self.offset
        self.console.work(lambda: client.call("ci.list", **params, offset=offset, page_size=100), loaded)

    def sort_column(self, column):
        key = COLUMNS[column][0]
        self.descending = not self.descending if self.sort_key == key else False
        self.sort_key = key
        self.table.horizontalHeader().setSortIndicator(column, Qt.SortOrder.DescendingOrder if self.descending else Qt.SortOrder.AscendingOrder)
        self.refresh(True)

    def page(self, amount):
        self.offset = max(0, self.offset+amount); self.refresh()

    def selected(self):
        indexed = {row["hostname"]:row for row in self.rows}
        return [indexed[self.table.item(index.row(),0).data(Qt.ItemDataRole.UserRole)] for index in self.table.selectionModel().selectedRows()]

    def collect(self):
        chosen = self.selected()
        self.console.start_job("ci_inventory", hosts_override=[r["hostname"] for r in chosen] if chosen else None)

    def edit_filtered(self):
        if not self.console.require_client(): return
        client = self.console.client; params = self.filters()
        def fetch():
            rows = []; offset = 0
            while True:
                data = client.call("ci.list", **params, offset=offset, page_size=200)
                rows.extend(data["rows"]); offset += len(data["rows"])
                if offset >= data["total"] or not data["rows"]: return rows
        self.console.work(fetch, lambda rows: self.edit(rows))

    def edit(self, provided=None):
        rows = provided if isinstance(provided, list) else self.selected()
        if not rows:
            QMessageBox.information(self, "장비 선택", "수정할 행을 선택하세요. Ctrl/Shift로 여러 장비를 선택할 수 있습니다."); return
        dialog = QDialog(self); dialog.setWindowTitle(f"CI 정보 편집 · {len(rows)}대"); dialog.resize(620,650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("체크한 속성만 변경합니다. 체크한 입력란을 비우면 해당 속성이 삭제됩니다. 날짜: YYYY-MM-DD"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); form = QFormLayout(body); editors = {}
        for key,label in FIELDS.items():
            check = QCheckBox(label)
            if key == "operational_status":
                edit = QComboBox(); edit.addItems(["", "운영", "유휴", "폐기"])
                if len(rows)==1: edit.setCurrentText(rows[0].get("manual", {}).get(key, ""))
            else:
                edit = QLineEdit(rows[0].get("manual", {}).get(key, "") if len(rows)==1 else "")
                edit.setMaxLength(4000 if key == "notes" else 256)
            edit.setEnabled(False); check.toggled.connect(edit.setEnabled)
            form.addRow(check,edit); editors[key] = (check,edit)
        scroll.setWidget(body); layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        patch = {key:(edit.currentText() if isinstance(edit,QComboBox) else edit.text()) for key,(check,edit) in editors.items() if check.isChecked()}
        if not patch: return
        client = self.console.client
        if not client: return
        def saved(result):
            self.console.status_line.setText(f"CI 저장: {len(result['updated'])}대 완료 / {len(result['failed'])}대 실패")
            if result['failed']: QMessageBox.warning(self,"일부 저장 실패", "\n".join(result['failed']))
            self.refresh()
        self.console.work(lambda: client.call("ci.update", hosts=[r['hostname'] for r in rows], patch=patch),saved)

    def details(self):
        rows = self.selected()
        if not rows: return
        row = rows[0]; flat = flattened(row)
        dialog = QDialog(self); dialog.resize(800,700); dialog.setWindowTitle("CI 상세 · "+row["hostname"])
        layout = QVBoxLayout(dialog); text = QPlainTextEdit(); text.setReadOnly(True)
        fields = {"hostname":"등록 hostname", "ip":"관리 IP", **AUTO_FIELDS, **FIELDS, "last_attempt":"최근 수집 시도", "last_success":"최근 수집 성공", "collection_status":"수집 상태", "error":"오류", "updated_at":"자산 정보 변경 시각", "observed_ip":"마지막 수집 관리 IP", "stale":"관리 IP 변경 여부"}
        text.setPlainText("\n\n".join(label+": "+value_text(display_value(key, flat.get(key))) for key,label in fields.items()))
        layout.addWidget(text); self.add_button(layout,"닫기",dialog.accept); dialog.exec()

    def export(self):
        if not self.console.require_client(): return
        path,kind = QFileDialog.getSaveFileName(self,"조회된 모든 CI 저장","ci-assets.xlsx","Excel (*.xlsx);;CSV (*.csv)")
        if not path: return
        client = self.console.client; params = self.filters()
        def save():
            columns = {"hostname":"Hostname", "ip":"관리 IP", **AUTO_FIELDS, **FIELDS, "last_attempt":"최근 수집 시도", "last_success":"최근 수집 성공", "collection_status":"수집 상태", "error":"오류", "stale":"관리 IP 변경 여부", "observed_ip":"마지막 수집 관리 IP", "updated_at":"자산 정보 변경 시각"}
            def records():
                yield list(columns.values())
                offset = 0
                while True:
                    data = client.call("ci.list", **params, offset=offset, page_size=200)
                    for row in data['rows']:
                        flat = flattened(row); yield [display_value(k, flat.get(k,"")) for k in columns]
                    offset += len(data['rows'])
                    if offset >= data['total'] or not data['rows']: break
            if kind.startswith("CSV") or path.lower().endswith('.csv'):
                with open(path,'w',encoding='utf-8-sig',newline='') as output:
                    writer = csv.writer(output)
                    for row in records(): writer.writerow([safe_csv(v) for v in row])
            else: write_report(path, [("CI 자산", records())])
            return path
        self.console.work(save, lambda result: self.console.status_line.setText("CI 저장 완료: "+result))

"""Native desktop control console; operational work stays on Linux."""
from __future__ import annotations

import argparse
import csv
import base64
import json
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QDateTime
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QProgressBar, QDialog, QFormLayout,
    QSpinBox, QDialogButtonBox, QFileDialog, QMessageBox, QPlainTextEdit, QSplitter,
    QTreeWidget, QTreeWidgetItem, QComboBox, QDateTimeEdit, QTabWidget, QScrollArea, QInputDialog, QMenu,
)

from desktop.client import ConnectionSettings, ServerClient
from desktop.graph import ConnectionMap
from desktop.connection_view import filter_snapshot, table_rows, table_page
from desktop.theme import LIGHT_CONTROLS, light_palette
from desktop.tables import enable_sorting, populate, row_identity, SortTreeItem

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #23344c; }
QMainWindow, QDialog, QMessageBox, #workspace { background: #f3f6fb; }
#sidebar { background: #ffffff; border-right: 1px solid #e0e7f0; }
#sidebar QLabel { color: #718198; background: transparent; border: none; }
#sidebar QPushButton { color: #465b75; text-align: left; background: transparent; border: 1px solid transparent; padding: 9px 12px; border-radius: 7px; font-size: 10pt; }
#sidebar QPushButton:checked { color: #1954ae; background: #eaf2ff; border-color: #d8e6fb; font-weight: 600; }
#sidebar QPushButton:hover { background: #f1f5fa; }
#sidebar QPushButton:checked:hover { background: #e2edff; }
#sidebar QLabel#brand { color: #233e64; font-size: 16pt; font-weight: 700; }
#sidebar QLabel#navCaption { color: #8b99ac; font-size: 8pt; font-weight: 600; }
#sidebar QLabel#serverStatus { color: #62758f; font-size: 9pt; }
#sidebar QPushButton#settingsButton { color: #536b88; background: #f6f8fc; border: 1px solid #e3eaf3; font-size: 9pt; padding: 7px 10px; }
#sidebar QPushButton#settingsButton:hover { background: #eaf1fa; border-color: #ccdbef; }
#settingsMenu { background: white; color: #233e64; border: 1px solid #d8e1ee; padding: 6px; }
#settingsMenu::item { padding: 9px 18px; border-radius: 5px; }
#settingsMenu::item:selected { color: #1954ae; background: #eaf2ff; }
#settingsMenu::item:disabled { color: #9aa8b8; }
#settingsMenu::separator { height: 1px; background: #e6edf5; margin: 5px 8px; }
#card { background: white; border: 1px solid #e0e7f0; border-radius: 12px; }
#title { font-size: 23pt; font-weight: 700; color: #122139; }
#subtitle { color: #77869c; }
#section { font-size: 13pt; font-weight: 600; }
#metric { font-size: 27pt; font-weight: 700; }
#badge { color: #177e6d; background: #e4f5ef; padding: 7px 12px; border-radius: 6px; }
QPushButton { background: white; border: 1px solid #d8e1ee; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #eaf0fb; border-color: #a9c0e8; }
QPushButton:disabled { color: #9ca9ba; background: #edf1f6; }
QPushButton[primary="true"] { background: #2869df; color: white; border: none; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #1c56bb; }
QPushButton[primary="true"]:disabled { color: #8796aa; background: #e3e9f2; }
QLineEdit, QSpinBox, QPlainTextEdit, QComboBox, QDateTimeEdit { border: 1px solid #d9e2ee; border-radius: 6px; background: white; padding: 8px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e6efff; selection-color: #203955; }
QSpinBox, QDateTimeEdit, QComboBox, QLineEdit { padding: 5px 8px; min-height: 28px; }
QTableWidget { background: white; border: none; gridline-color: #edf1f6; selection-background-color: #e6efff; selection-color: #203955; }
QHeaderView::section { background: #f7f9fc; color: #6a7c93; border: none; border-bottom: 1px solid #e1e8f0; padding: 9px; font-size: 9pt; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #eff3f7; }
QProgressBar { border: none; border-radius: 4px; background: #e9eff8; height: 8px; text-align: center; }
QProgressBar::chunk { background: #2a74df; border-radius: 4px; }
QCheckBox { spacing: 8px; }
QTabWidget::pane { background: white; border: 1px solid #d9e2ee; border-radius: 6px; }
QTabBar::tab { background: #edf2f8; color: #23344c; border: 1px solid #d9e2ee; padding: 9px 14px; }
QTabBar::tab:selected { background: white; color: #122139; border-bottom: 3px solid #2869df; font-weight: 600; }
QTabBar::tab:hover { background: #e6efff; color: #122139; }
#accountPage { background: white; color: #23344c; }
#accountPage QLabel, #accountPage QCheckBox { background: transparent; color: #23344c; }
QSplitter::handle { background: transparent; width: 12px; }
"""
BASE_STYLE = STYLE
STYLE += LIGHT_CONTROLS


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.clicked.connect(callback)
    return widget


def card():
    frame = QFrame(); frame.setObjectName("card")
    layout = QVBoxLayout(frame); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
    return frame, layout


def table(headers, sortable=True):
    widget = QTableWidget(0, len(headers)); widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide(); widget.setShowGrid(False)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.verticalHeader().setDefaultSectionSize(39)
    if sortable: enable_sorting(widget)
    return widget


def fill_table(widget, rows):
    populate(widget, rows)


def fill_identity_table(widget, records, rows):
    identity = row_identity(widget)
    populate(widget, rows, [record["id"] for record in records])
    widget.clearSelection(); widget.setCurrentCell(-1,-1)
    for index in range(widget.rowCount()):
        if row_identity(widget,index) == identity:
            widget.setCurrentCell(index,0); widget.selectRow(index)



class PageStack(QWidget):
    """Only the active page participates in layout size constraints."""
    def __init__(self):
        super().__init__(); self._pages = []; self._index = -1
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)

    def addWidget(self, page):
        page.setParent(self); page.hide(); self._pages.append(page)
        if self._index < 0: self.setCurrentIndex(0)
        return len(self._pages)-1

    def count(self): return len(self._pages)
    def currentIndex(self): return self._index
    def currentWidget(self): return self._pages[self._index] if self._index >= 0 else None
    def widget(self, index): return self._pages[index]

    def setCurrentIndex(self, index):
        if index == self._index: return
        old = self.currentWidget()
        if old is not None:
            self.layout().removeWidget(old); old.hide()
        self._index = index
        page = self.currentWidget(); self.layout().addWidget(page); page.show()
        self.updateGeometry()


class WorkerSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:
            self.deliver(self.signals.error, str(exc))
        else:
            self.deliver(self.signals.done, result)

    @staticmethod
    def deliver(signal, value):
        try:
            signal.emit(value)
        except RuntimeError as exc:
            if "Signal source has been deleted" not in str(exc):
                raise


class ConnectDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.setWindowTitle("Connect to Linux main server"); self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Connect your control console", "section"))
        note = label("A dedicated TLS port connects this console to Linux.\nTarget SSH credentials remain on the Linux server.", "subtitle")
        layout.addWidget(note)
        form = QFormLayout()
        self.host = QLineEdit(); self.host.setPlaceholderText("sm-main.example.internal")
        self.port = QSpinBox(); self.port.setRange(1024, 65535); self.port.setValue(7443)
        self.login_id = QLineEdit(); self.login_id.setPlaceholderText("SERVER login ID")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Server IP", self.host); form.addRow("Port", self.port)
        form.addRow("ID", self.login_id); form.addRow("Password", self.password)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def settings(self):
        return ConnectionSettings(self.host.text().strip(), self.port.value(), "", "",
                                  self.login_id.text().strip(), self.password.text())


class InventoryDialog(QDialog):
    def __init__(self, parent, rows, profiles=None):
        super().__init__(parent); self.setWindowTitle("Manage server inventory"); self.resize(960, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Saved encrypted on the Linux main server.", "subtitle"))
        layout.addWidget(label("Double-click hostname, IP or OS to edit. Choose an SSH profile configured on Linux.", "subtitle"))
        self.grid = table(["Hostname", "IP address", "Operating system", "SSH profile"], sortable=False)
        self.grid.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        self.grid.verticalHeader().setDefaultSectionSize(44)
        self.profiles = sorted(set(profiles or ["default"]) | {"default"})
        fill_table(self.grid, [[r["hostname"], r["ip"], r["os"], r.get("profile", "default")] for r in rows]); layout.addWidget(self.grid)
        for index, row in enumerate(rows):
            self.profile_selector(index, row.get("profile") or "default")
        actions = QHBoxLayout()
        actions.addWidget(button("Add server", self.add_server))
        actions.addWidget(button("Remove selected", self.remove)); actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def profile_selector(self, row, selected="default"):
        selector = QComboBox()
        for profile in self.profiles:
            selector.addItem(profile, profile)
        if selected not in self.profiles:
            selector.addItem(selected + " (not configured)", selected)
        selector.setCurrentIndex(selector.findData(selected))
        self.grid.setCellWidget(row, 3, selector)

    def add_server(self):
        row = self.grid.rowCount()
        self.grid.insertRow(row)
        self.profile_selector(row)

    def remove(self):
        for row in sorted({item.row() for item in self.grid.selectedItems()}, reverse=True):
            self.grid.removeRow(row)

    def accept(self):
        missing = [str(index + 1) for index, row in enumerate(self.rows()) if row["profile"] not in self.profiles]
        if missing:
            QMessageBox.information(self, "Choose configured SSH profiles",
                                    "Choose a configured Linux SSH profile for rows: " + ", ".join(missing))
            return
        super().accept()

    def rows(self):
        return [{key: self.grid.cellWidget(row, col).currentData() if col == 3 else
                 (self.grid.item(row, col).text().strip() if self.grid.item(row, col) else "")
                 for col, key in enumerate(("hostname", "ip", "os", "profile"))} for row in range(self.grid.rowCount())]


class Console(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.setPalette(light_palette())
        self.setWindowTitle("SM Automation | Control Console")
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1460, area.width()-30), min(920, area.height()-40)); self.setMinimumSize(800, 540)
        self.client = None; self.demo = demo; self.servers = []; self.equipment_books=[]; self.jobs = []; self.connection_results = []; self.connection_cache = {}; self.connection_cache_loading=False
        self.active_job = None; self.loaded_job = None; self.poll_busy = False; self.epoch = 0
        self.backup_history = {}
        self.backup_history_offset = 0
        self.history_errors = []
        self.submission_pending = False
        self.job_history = {}; self.job_history_offset = 100
        self.resource_loaded_job = None
        self.workers = set()
        self.build_ui()
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(15000)
        self.agent_inventory_busy=False
        self.agent_inventory_timer=QTimer(self);self.agent_inventory_timer.timeout.connect(self.refresh_agent_inventory);self.agent_inventory_timer.start(30000)
        self.resource_timer = QTimer(self); self.resource_timer.timeout.connect(self.refresh_resources); self.resource_timer.setInterval(120000)
        if demo:
            self.load_demo()

    def build_ui(self):
        base = QWidget(); self.setCentralWidget(base)
        root = QHBoxLayout(base); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); self.sidebar = sidebar
        nav = QVBoxLayout(sidebar); nav.setContentsMargins(14, 22, 14, 16); nav.setSpacing(4)
        nav.addWidget(label("SM Automation", "brand"))
        nav.addWidget(label("INFRASTRUCTURE CONSOLE", "navCaption")); nav.addSpacing(18)
        nav.addWidget(label("WORKSPACE", "navCaption")); nav.addSpacing(4)
        self.nav_buttons = []
        for index, title in enumerate(["01   Overview", "02   Connection map", "03   Backups", "04   Activity", "05   Accounts", "06   Patches", "07   Schedules", "08   Resources", "09   Commands / Files", "10   CI / 자산"]):
            item = QPushButton(title); item.setCheckable(True)
            item.clicked.connect(lambda _, value=index: self.navigate(value)); nav.addWidget(item); self.nav_buttons.append(item)
        nav.addStretch(1)
        divider=QFrame();divider.setFrameShape(QFrame.Shape.HLine);divider.setStyleSheet("background:#e5ebf3;max-height:1px;border:0;")
        nav.addWidget(divider);nav.addSpacing(8)
        self.server_badge = label("Not connected", "serverStatus"); self.server_badge.setWordWrap(True); nav.addWidget(self.server_badge)
        self.settings_menu=QMenu(self);self.settings_menu.setObjectName("settingsMenu")
        self.settings_menu.addAction("SERVER 연결", self.connect_server)
        self.settings_menu.addAction("연결 해제", self.disconnect_server)
        self.settings_menu.addSeparator()
        self.settings_menu.addAction("CLIENT 접속 계정 설정", self.edit_client_credentials)
        self.settings_menu.addAction("SERVER GUI 계정 설정", self.edit_gui_account)
        self.settings_menu.addAction("SERVER 공개키 배포", self.deploy_server_key)
        self.settings_menu.addSeparator()
        self.agent_setup_action=self.settings_menu.addAction("Windows CLIENT 설치 / 상태", self.agent_setup)
        self.settings_button=QPushButton("설정 및 연결");self.settings_button.setObjectName("settingsButton")
        self.settings_button.setToolTip("SERVER 연결 · 접속 계정 · 공개키 · Windows CLIENT 설치/상태")
        self.settings_button.setMenu(self.settings_menu);nav.addWidget(self.settings_button)
        self.sidebar_scroll = QScrollArea(); self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setStyleSheet("QScrollArea {background:#ffffff;border:0;}")
        self.sidebar_scroll.setFixedWidth(228); self.sidebar_scroll.setWidget(sidebar)
        root.addWidget(self.sidebar_scroll)
        workspace = QWidget(); workspace.setObjectName("workspace")
        self.workspace_scroll = QScrollArea(); self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setWidget(workspace); root.addWidget(self.workspace_scroll, 1)
        content = QVBoxLayout(workspace); content.setContentsMargins(28, 24, 28, 18); content.setSpacing(18)
        top = QHBoxLayout(); top.addWidget(label("OPERATIONS  /  INFRASTRUCTURE", "subtitle")); top.addStretch()
        self.connection_badge = label("OFFLINE", "badge"); top.addWidget(self.connection_badge); self.zoom_control = QSpinBox(); self.zoom_control.setRange(60, 140); self.zoom_control.setValue(90); self.zoom_control.setSuffix("%"); self.zoom_control.setKeyboardTracking(False); self.zoom_control.setToolTip("Type a percentage, then press Enter to apply")
        self.zoom_control.valueChanged.connect(self.manual_zoom)
        top.addWidget(label("Zoom")); top.addWidget(self.zoom_control)
        self.auto_fit = QCheckBox("자동 맞춤"); self.auto_fit.setChecked(True)
        self.auto_fit.setToolTip("창과 화면 크기에 맞춰 배율을 자동 조절합니다. 숫자 입력은 수동 배율로 전환합니다.")
        self.auto_fit.toggled.connect(lambda enabled: self.fit_window() if enabled else None); top.addWidget(self.auto_fit)
        top.addWidget(button("Save query results", lambda: self.export_widgets(self.pages.currentWidget()))); content.addLayout(top)
        scope=QHBoxLayout();scope.addWidget(label("실행 대상"));self.book_selector=QComboBox();self.book_selector.addItem("개별 장비 선택",None);self.book_selector.setMinimumWidth(280)
        self.book_selector.currentIndexChanged.connect(self.apply_book_selection);scope.addWidget(self.book_selector)
        scope.addWidget(button("장비록 관리",self.manage_books));scope.addWidget(button("장비록 새로고침",self.refresh_books));scope.addStretch();content.addLayout(scope)
        self.title = label("Infrastructure overview", "title"); content.addWidget(self.title)
        self.subtitle = label("Windows · Linux · AIX 통합 관리 콘솔 | 중앙 SERVER에서 작업과 이력을 관리합니다.", "subtitle"); content.addWidget(self.subtitle)
        metrics = QHBoxLayout(); metrics.setSpacing(14)
        self.metric_values = []
        self.metric_cards = []
        for title, value, foot in [("INVENTORY", "0", "Managed servers"), ("SELECTED", "0", "Ready for collection"),
                                    ("ESTABLISHED", "—", "Latest connection snapshot"), ("STORAGE", "Encrypted", "Linux DATA + BACKUP")]:
            frame, layout = card(); layout.addWidget(label(title, "subtitle")); number = label(value, "metric")
            if value == "Encrypted":
                number.setStyleSheet("font-size:22pt;color:#118875;font-weight:700")
            layout.addWidget(number); layout.addWidget(label(foot, "subtitle")); metrics.addWidget(frame)
            self.metric_cards.append(frame)
            self.metric_values.append(number)
        content.addLayout(metrics)
        self.pages = PageStack(); content.addWidget(self.pages, 1)
        self.build_overview(); self.build_network(); self.build_backup(); self.build_activity(); self.build_accounts(); self.build_patches(); self.build_schedules(); self.build_resources(); self.build_tools()
        from desktop.ci import CIDashboard
        self.ci_dashboard = CIDashboard(self); self.pages.addWidget(self.ci_dashboard)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.setMaximumHeight(6); content.addWidget(self.progress)
        self.status_line = label("Connect to a Linux main server to load your inventory.", "subtitle"); content.addWidget(self.status_line)
        self.navigate(0)
        self.fit_timer = QTimer(self); self.fit_timer.setSingleShot(True); self.fit_timer.timeout.connect(self.fit_window)
        self.set_zoom(90)

    def manual_zoom(self, percent):
        self.auto_fit.setChecked(False)
        self.set_zoom(percent)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "fit_timer"):
            self.fit_timer.start(80)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "fit_timer"):
            self.fit_timer.start(80)

    def fit_window(self):
        if not self.auto_fit.isChecked(): return
        percent = max(60, min(90, round(90 * min(self.width()/1460, self.height()/920))))
        self.set_zoom(percent)
        self.sidebar.layout().activate()
        needed = self.sidebar.layout().minimumSize().height()
        available = max(1,self.sidebar_scroll.viewport().height())
        if needed > available:
            percent = max(60, min(percent, int(percent*available/needed)))
            self.set_zoom(percent)
        self.zoom_control.blockSignals(True); self.zoom_control.setValue(percent); self.zoom_control.blockSignals(False)
        self.sidebar_scroll.ensureWidgetVisible(self.nav_buttons[self.pages.currentIndex()])

    def set_zoom(self, percent):
        scale = percent / 100
        self.setStyleSheet(re.sub(r"(\d+(?:\.\d+)?)(px|pt)",
                                 lambda match: str(round(float(match[1]) * scale, 2)) + match[2], BASE_STYLE) + LIGHT_CONTROLS)
        for widget in self.findChildren(QPushButton):
            widget.setMinimumHeight(widget.fontMetrics().lineSpacing() + round(12*scale) + 6)
        for widget in self.findChildren(QLineEdit) + self.findChildren(QSpinBox) + self.findChildren(QComboBox):
            widget.setMinimumHeight(widget.fontMetrics().lineSpacing() + round(10*scale) + 6)
        # Qt layout margins are independent of stylesheet dimensions.
        for layout in self.findChildren(QVBoxLayout) + self.findChildren(QHBoxLayout) + self.findChildren(QFormLayout):
            if layout.property("original_spacing") is None:
                layout.setProperty("original_spacing", layout.spacing())
                margins = layout.contentsMargins()
                layout.setProperty("original_margins", [margins.left(), margins.top(), margins.right(), margins.bottom()])
            spacing = layout.property("original_spacing")
            if spacing >= 0:
                layout.setSpacing(round(spacing * scale))
            layout.setContentsMargins(*[round(value * scale) for value in layout.property("original_margins")])
        margins=self.sidebar.layout().contentsMargins()
        widest=max(item.sizeHint().width() for item in self.nav_buttons+[self.settings_button])
        brand_width=self.sidebar.findChild(QLabel,"brand").sizeHint().width()
        self.sidebar_scroll.setFixedWidth(max(216,widest+ margins.left()+margins.right()+22,brand_width+margins.left()+margins.right()+22))
        for widget in self.findChildren(QTableWidget):
            row_height = max(round(44 * scale), widget.fontMetrics().lineSpacing() + round(14 * scale) + 8)
            widget.verticalHeader().setDefaultSectionSize(row_height)
            if widget in (self.target_table, self.account_targets):
                for row in range(widget.rowCount()):
                    if widget is self.target_table:
                        widget.setRowHeight(row, max(round(60 * scale), 2 * widget.fontMetrics().height() + 12))

    def closeEvent(self,event):
        for name in ("timer","resource_timer","agent_inventory_timer","fit_timer"):
            if hasattr(self,name):getattr(self,name).stop()
        super().closeEvent(event)

    def agent_setup(self):
        if not self.require_client():return
        from desktop.agent_setup import AgentDialog
        AgentDialog(self).exec()

    def refresh_agent_inventory(self):
        if not self.client or self.demo or self.agent_inventory_busy:return
        client=self.client;self.agent_inventory_busy=True
        def loaded(rows):
            self.agent_inventory_busy=False;self.set_inventory(rows)
            if self.pages.currentIndex()==9:self.ci_dashboard.refresh()
        self.work(lambda:client.call("inventory.list"),loaded,quiet=True,on_error=lambda:setattr(self,"agent_inventory_busy",False))

    def edit_gui_account(self):
        if not self.require_client():
            return
        dialog = QDialog(self); dialog.setWindowTitle("SM Automation SERVER login account"); dialog.resize(510, 240)
        layout = QVBoxLayout(dialog); form = QFormLayout()
        username = QLineEdit(); password = QLineEdit(); password.setEchoMode(QLineEdit.EchoMode.Password)
        role = QComboBox(); role.addItem("관리자 — 전체 관리", "admin"); role.addItem("운영자 — 공유폴더 전송·조회", "operator"); role.addItem("조회자 — 공유폴더 조회·다운로드", "viewer")
        accounts = QComboBox(); accounts.addItem("새 계정", None)
        def select_account(index):
            data=accounts.itemData(index)
            if data:
                username.setText(data["id"]);role.setCurrentIndex(role.findData(data["role"]))
            else: username.clear()
        accounts.currentIndexChanged.connect(select_account)
        def list_accounts(rows):
            for row in rows: accounts.addItem(row["id"] + " — " + row["role"],row)
        self.work(lambda:self.client.call("gui.account.list"),list_accounts)
        form.addRow("계정 목록",accounts)
        form.addRow("ID", username); form.addRow("Password", password); form.addRow("Role", role); layout.addLayout(form)
        password.setPlaceholderText("기존 계정은 빈칸이면 비밀번호 유지")
        note = label("Create an application login or update its password. This account controls this SERVER; it is separate from CLIENT SSH accounts.")
        note.setWordWrap(True); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            client = self.client; login = username.text().strip(); secret = password.text(); password.clear()
            self.work(lambda: client.call("gui.account.save", username=login, password=secret, role=role.currentData()),
                      lambda _: self.status_line.setText("SERVER GUI login account saved: " + login))
        else:
            password.clear()

    def edit_client_credentials(self):
        if not self.require_client():
            return
        hosts = self.checked_hosts()
        if len(hosts) != 1:
            QMessageBox.information(self, "CLIENT login settings", "Select exactly one CLIENT in Connection map."); return
        if any(r["hostname"]==hosts[0] and r.get("transport")=="agent" for r in self.servers):
            QMessageBox.information(self,"Windows agent","이 장비는 에이전트 인증을 사용하므로 SSH 계정/비밀번호 설정이 필요하지 않습니다.");return
        client = self.client; hostname = hosts[0]
        def show(current):
            dialog = QDialog(self); dialog.setWindowTitle("CLIENT login: " + hostname); dialog.resize(530, 300)
            layout = QVBoxLayout(dialog); form = QFormLayout()
            layout.addWidget(label(hostname + " / " + current["ip"]))
            user = QLineEdit(current["user"]); port = QSpinBox(); port.setRange(1, 65535); port.setValue(current["port"])
            use_password = QCheckBox("Use password authentication"); use_password.setChecked(current["password_saved"])
            password = QLineEdit(); password.setEchoMode(QLineEdit.EchoMode.Password)
            password.setPlaceholderText("Saved password retained if blank" if current["password_saved"] else "Enter password")
            form.addRow("CLIENT SSH account", user); form.addRow("SSH port", port)
            form.addRow(use_password); form.addRow("Password", password); layout.addLayout(form)
            note = label("Encrypted on Linux SERVER. Password is never returned to the GUI. Uncheck to use the existing SSH key/profile.")
            note.setWordWrap(True); layout.addWidget(note)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                params = {"hostname": hostname, "user": user.text().strip(), "port": port.value(),
                          "use_password": use_password.isChecked(), "password": password.text()}
                password.clear()
                self.work(lambda: client.call("client.credentials.save", **params),
                          lambda _: self.status_line.setText("CLIENT login settings saved on Linux: " + hostname))
            else:
                password.clear()
        self.work(lambda: client.call("client.credentials.get", hostname=hostname), show)

    def build_overview(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Your server fleet", "section"))
        actions = QHBoxLayout()
        actions.addWidget(button("Manage inventory", self.edit_inventory)); actions.addWidget(button("Import CSV / Excel", self.import_csv)); actions.addWidget(button("Download clients Excel", self.export_inventory_excel))
        actions.addWidget(button("Refresh", self.reload)); actions.addWidget(button("OS별 지원 범위", self.show_platform_support)); actions.addStretch()
        actions.addWidget(button("Resource snapshot", lambda: (self.navigate(7), self.start_job("monitoring"))))
        actions.addWidget(button("Security audit", lambda: self.start_job("security_audit")))
        actions.addWidget(button("Protect SSH config (600)", lambda: self.start_job("security_permissions")))
        actions.addWidget(button("Preview SSH policy", lambda: self.start_job("security_plan")))
        body.addLayout(actions)
        self.inventory_table = table(["Hostname", "IP address", "Operating system", "Execution"]); body.addWidget(self.inventory_table)
        body.addWidget(label("Inventory changes and collection results are stored encrypted on Linux.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def show_platform_support(self):
        dialog=QDialog(self);dialog.setWindowTitle("Windows · Linux · AIX 지원 범위");dialog.resize(790,480)
        body=QVBoxLayout(dialog);text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText("""CLIENT = 관리 대상 Windows / Linux / AIX 장비
SERVER = 중앙 작업·예약·암호화 저장을 담당하는 Linux 서버
GUI = Windows 관리 콘솔

공통: 목록·장비록·CI·TCP 연결 지도·원격 명령·파일 전송·백업·비교
Windows 명령: PowerShell / SYSTEM. 파일 전송은 현재 8 MiB 제한.
Linux/AIX 명령: SSH 셸 및 설정된 실행 권한.

05 계정: Windows 로컬 계정 조회 전용 / Linux 조회·변경 / AIX 계정·그룹·잠금 조회 전용
06 패치: Windows 설치 KB 조회 전용 / Linux 배포판별 조회·계획·적용 / AIX OS 수준·파일셋·임시 수정 조회 전용
08 자원: Windows CPU·물리 메모리·시스템 디스크·가동시간 / Linux·AIX 지원. Linux 보안 정책: Linux 전용

Windows KB는 Get-HotFix/CBS 기록이며 미설치 업데이트·전체 앱·드라이버 목록이 아닙니다.
검증 완료 범위: 현재 Windows PC와 로컬 WSL. AIX/RHEL 실장비 검증은 미실행.
지원되지 않는 기능이 모든 OS에서 동작하는 것으로 표시하지 않습니다.""")
        body.addWidget(text);body.addWidget(button("닫기",dialog.accept));dialog.exec()

    def build_resources(self):
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Windows / Linux / AIX resource snapshots", "section"))
        actions = QHBoxLayout()
        actions.addWidget(button("Collect resources", lambda: self.start_job("monitoring"), True))
        self.resource_auto = QCheckBox("Refresh every 120 seconds while this console is open")
        def auto(enabled):
            if enabled:
                self.resource_timer.start(); self.refresh_resources()
            else:
                self.resource_timer.stop()
        self.resource_auto.toggled.connect(auto); actions.addWidget(self.resource_auto); actions.addStretch()
        body.addLayout(actions)
        self.resource_updated = label("No resource snapshot loaded", "subtitle"); body.addWidget(self.resource_updated)
        self.resource_table = table(["Server", "Load (Linux/AIX) / CPU % (Windows)", "Memory used", "Root / Windows system disk used", "Uptime / status"])
        body.addWidget(self.resource_table, 1)
        note = label("Windows: CPU 사용률·OS 물리 메모리·시스템 드라이브 조회. Linux/AIX: Load 조회. AIX 메모리 사용량은 전체-무료(파일 캐시 포함), Linux available과 다릅니다. Load는 CPU 사용률이 아닙니다. 자동 조회는 다른 작업 완료 후 수행합니다.", "subtitle")
        note.setWordWrap(True); body.addWidget(note)
        layout.addWidget(frame); self.pages.addWidget(page)

    def refresh_resources(self):
        if not self.client or self.demo or not self.checked_hosts():
            return
        if any(job["status"] in {"queued", "running"} for job in self.jobs):
            return
        self.start_job("monitoring")

    def display_resources(self, rows, observed_at=""):
        values = []
        for row in rows:
            result = row.get("result", {})
            if row.get("status") != "completed":
                values.append([row["hostname"], "Unavailable", "", "", row.get("error", row["status"])]); continue
            memory = result.get("memory_mb", {}); filesystem = result.get("root_filesystem", {})
            total, used = memory.get("total", 0), memory.get("used", 0)
            percentage = round(100 * used / total) if total else 0
            cpu = (f"CPU {result['cpu_percent']:.1f}%" if "cpu_percent" in result else " / ".join(f"{value:.2f}" for value in result.get("load_average", [])))
            values.append([row["hostname"], cpu,
                           f"{percentage}% ({used:,} / {total:,} MiB)", filesystem.get("capacity", "Unavailable"), result.get("uptime", "Unavailable")])
        sorting=self.resource_table.isSortingEnabled();self.resource_table.setSortingEnabled(False)
        fill_table(self.resource_table, values)
        for index, row in enumerate(rows):
            if row.get("status") != "completed":
                continue
            result = row.get("result", {}); memory = result.get("memory_mb", {})
            for column, value in [(2, round(100 * memory.get("used", 0) / max(1, memory.get("total", 0)))),
                                  (3, int(result.get("root_filesystem", {}).get("capacity", "0%").rstrip("%")))]:
                progress = QProgressBar(); progress.setRange(0, 100); progress.setValue(max(0, min(100, value)))
                progress.setFormat(values[index][column]); progress.setToolTip(values[index][column])
                if value >= 90:
                    progress.setStyleSheet("QProgressBar::chunk { background: #d95f4a; }")
                self.resource_table.setCellWidget(index, column, progress)
        self.resource_table.setSortingEnabled(sorting)
        self.resource_updated.setText("Snapshot collected: " + (observed_at or "synthetic preview"))

    def build_network(self):
        page = QWidget(); layout = QHBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(16)
        selection, left = card(); selection.setFixedWidth(260)
        left.addWidget(label("Collection targets", "section"))
        self.server_search = QLineEdit(); self.server_search.setPlaceholderText("Find a server...")
        self.server_search.textChanged.connect(self.filter_servers); left.addWidget(self.server_search)
        self.select_all = QCheckBox("Select all servers"); self.select_all.setChecked(True)
        self.select_all.toggled.connect(self.check_all); left.addWidget(self.select_all)
        self.target_table = table(["", "Server"])
        self.target_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.target_table.setColumnWidth(0, 30); self.target_table.horizontalHeader().hide()
        self.target_table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self.filter_servers(self.server_search.text()))
        self.target_table.itemChanged.connect(self.selection_changed); left.addWidget(self.target_table)
        left.addWidget(button("새로 수집 (선택 장비 접속)", lambda: self.start_job("connections"), True))
        left.addWidget(button("저장 결과 다시 불러오기",self.restore_connection_cache))
        note = label("체크는 저장 결과만 표시합니다. 새로 수집 버튼만 장비에 접속합니다.\nLinux executes netstat over SSH.\nOnly ESTABLISHED TCP peers\nare displayed.", "subtitle"); left.addWidget(note)
        layout.addWidget(selection)
        right_frame, right = card()
        tools = QHBoxLayout(); tools.addWidget(label("Connection mind map", "section")); tools.addStretch()
        self.peer_search = QLineEdit(); self.peer_search.setPlaceholderText("Filter peer / port"); self.peer_search.setMaximumWidth(180)
        self.map_filter_timer=QTimer(self); self.map_filter_timer.setSingleShot(True); self.map_filter_timer.setInterval(250)
        self.map_filter_timer.timeout.connect(self.update_map)
        self.peer_search.textChanged.connect(lambda *_: self.map_filter_timer.start()); tools.addWidget(self.peer_search)
        tools.addWidget(button("Fit", lambda: self.graph.fit_map())); right.addLayout(tools)
        topology_note=label("여러 서버는 서버별 연결을 함께 표시합니다. 공통 상대 노드를 합치는 교차 토폴로지는 아닙니다.","subtitle"); topology_note.setWordWrap(True); right.addWidget(topology_note)
        paging=QHBoxLayout()
        self.map_page=QSpinBox(); self.map_page.setRange(1,1); self.map_page.setKeyboardTracking(False); self.map_page.valueChanged.connect(self.render_connection_pages)
        paging.addWidget(label("지도 페이지 (10대)")); paging.addWidget(self.map_page); right.addLayout(paging)
        self.graph = ConnectionMap(); self.graph.set_results([]); right.addWidget(self.graph, 1)
        right.addWidget(label("Blue = selected host / Green = peer / ↔ = TCP session / Local port ↔ peer port / Scroll to zoom, drag to pan", "subtitle"))
        self.connection_table = table(["Source", "Local endpoint", "Connected peer", "Port", "조회 시각"])
        self.connection_table.setMaximumHeight(170); right.addWidget(self.connection_table)
        paging=QHBoxLayout(); self.connection_page=QSpinBox(); self.connection_page.setRange(1,1); self.connection_page.setKeyboardTracking(False); self.connection_page.valueChanged.connect(self.render_connection_table)
        self.connection_count=label("조회 0건", "subtitle"); self.connection_count.setWordWrap(True); paging.addWidget(self.connection_count); paging.addStretch(); paging.addWidget(label("표 페이지 (200건)")); paging.addWidget(self.connection_page); right.addLayout(paging)
        self.map_generation=0; self.filtered_connections=[]
        layout.addWidget(right_frame, 1); self.pages.addWidget(page)

    def build_backup(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Configuration & account backups", "section"))
        text = label("Capture files and command output from every listed server.\nLinux encrypts each artifact under BACKUP / date / hostname / run ID.", "subtitle")
        text.setWordWrap(True); body.addWidget(text)
        coverage = table(["Operating system", "Configuration files", "Command snapshots"])
        fill_table(coverage, [["Linux", "sudoers + sudoers.d, SSH, PAM, cron, network", "chage per account, sudo privileges, services, storage"],
                             ["AIX", "security, filesystems, inittab, SSH, sudoers", "lsuser expiry, sudo privileges, lsvg, lssrc, packages"],
                             ["Windows agent 1.1 / SSH", "OpenSSH, hosts, GroupPolicy, scheduled tasks", "Local users, expiry, firewall, audit, patches"]])
        coverage.setMaximumHeight(175); body.addWidget(coverage)
        self.backup_root_password=QLineEdit(); self.backup_root_password.setEchoMode(QLineEdit.EchoMode.Password); self.backup_root_password.setPlaceholderText("선택: sudo 불가 시 su에 사용할 root 비밀번호 (작업 중 메모리에만 보관)"); body.addWidget(self.backup_root_password)
        actions = QHBoxLayout(); actions.addWidget(button("Back up ALL servers", lambda: self.start_job("backup", all_hosts=True, options={"root_password":self.backup_root_password.text()}), True))
        actions.addWidget(button("Back up selected", lambda: self.start_job("backup",options={"root_password":self.backup_root_password.text()}))); actions.addStretch(); body.addLayout(actions)
        history = QHBoxLayout()
        history.addWidget(button("Refresh backup history", lambda: self.load_backup_history(True)))
        history.addWidget(button("Load older backups", self.load_backup_history))
        history.addWidget(button("선택 백업 ↔ 현재 설정 비교",self.compare_backup))
        history.addStretch(); body.addLayout(history)
        self.backup_table = table(["Created", "Status", "Progress", "Job ID"]); body.addWidget(self.backup_table)
        self.backup_table.cellDoubleClicked.connect(lambda row, _: self.show_job(row_identity(self.backup_table,row)))
        body.addWidget(label("Double-click a backup to view Linux paths and per-artifact results. Partial captures are never reported as complete.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def compare_backup(self):
        row=self.backup_table.currentRow()
        if row<0 or row>=len(getattr(self,"backup_jobs",[])):
            self.status_line.setText("기준 백업을 목록에서 선택하고 대상 장비/장비록을 지정하세요.");return
        self.start_job("backup_compare",options={"baseline_job_id":row_identity(self.backup_table,row),"root_password":self.backup_root_password.text()})

    def build_activity(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Server-side job history", "section"))
        body.addWidget(button("Load older operations", self.load_job_history))
        self.jobs_table = table(["Created", "Operation", "Status", "Progress", "Job ID", "Details"])
        self.jobs_table.cellDoubleClicked.connect(lambda row, _: self.show_job(row_identity(self.jobs_table,row)))
        body.addWidget(self.jobs_table)
        body.addWidget(button("Cancel pending targets of selected job", self.cancel_selected_job))
        body.addWidget(label("Closing this console does not stop Linux jobs. Reconnect to see results.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def export_widgets(self, parent):
        rows = []
        for widget in parent.findChildren(QTableWidget):
            if widget in (self.account_targets, self.target_table):
                continue
            rows.append(["Table", *[widget.horizontalHeaderItem(c).text() for c in range(widget.columnCount())]])
            if widget is getattr(self,"connection_table",None):
                rows.extend(["",*values] for values in table_rows(self.filtered_connections))
                continue
            for r in range(widget.rowCount()):
                if not widget.isRowHidden(r):
                    rows.append(["", *[widget.item(r, c).text() if widget.item(r, c) else "" for c in range(widget.columnCount())]])
        for widget in parent.findChildren(QPlainTextEdit):
            if widget.isReadOnly() and widget is not getattr(self, "command_details", None):
                rows.append(["Text result", widget.toPlainText()])
        for widget in parent.findChildren(QTreeWidget):
            rows.append(["Tree", *[widget.headerItem().text(c) for c in range(widget.columnCount())]])
            def visit(item):
                rows.append(["", *[item.text(c) for c in range(widget.columnCount())]])
                for i in range(item.childCount()):
                    visit(item.child(i))
            for i in range(widget.topLevelItemCount()):
                visit(widget.topLevelItem(i))
        path, _ = QFileDialog.getSaveFileName(self, "Save displayed results", "results.csv", "CSV (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            try:
                with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                    csv.writer(stream).writerows([["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for v in row] for row in rows])
            except OSError:
                QMessageBox.warning(self, "Export failed", "Check the destination and permissions.")

    def build_tools(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(label("Commands · Linux/AIX root / Windows agent SYSTEM PowerShell", "section"))
        self.command_targets = QLabel(); self.command_targets.setWordWrap(True); layout.addWidget(self.command_targets)
        layout.addWidget(button("Choose servers in Connection map", lambda: self.navigate(1)))
        self.command_input = QPlainTextEdit(); self.command_input.setPlaceholderText("Command executed as root (sudo first, then su fallback)")
        saved = QHBoxLayout(); self.saved_commands = QComboBox()
        self.saved_commands.setMinimumWidth(200); saved.addWidget(self.saved_commands)
        saved.addWidget(button("목록 새로고침", self.refresh_saved_commands))
        saved.addWidget(button("불러오기", self.load_saved_command))
        saved.addWidget(button("현재 명령 저장", self.save_command))
        saved.addWidget(button("삭제", self.delete_saved_command)); layout.addLayout(saved)
        layout.addWidget(self.command_input); self.command_run_button=button("Run command", self.run_command, True); layout.addWidget(self.command_run_button)
        layout.addWidget(label("Target results appear below. Select a row for details."))
        self.command_results_panel = QWidget(); results_layout = QVBoxLayout(self.command_results_panel)
        self.command_results_table = table(["CLIENT", "Status", "Exit code", "Stdout", "Stderr / error"])
        self.command_results_table.setMinimumHeight(140)
        self.command_results_table.itemSelectionChanged.connect(self.show_command_detail)
        results_layout.addWidget(self.command_results_table)
        self.command_details = QPlainTextEdit(); self.command_details.setReadOnly(True); self.command_details.setMinimumHeight(110)
        results_layout.addWidget(self.command_details)
        results_layout.addWidget(button("Download detailed results CSV", lambda: self.export_widgets(self.command_results_panel)))
        layout.addWidget(self.command_results_panel)
        layout.addWidget(label("CLIENT (managed target) ↔ SERVER (Linux main server)", "section"))
        self.linux_file_path = QLineEdit(); self.linux_file_path.setPlaceholderText("SERVER absolute path: /tmp/server-file.txt")
        self.client_file_path = QLineEdit(); self.client_file_path.setPlaceholderText("CLIENT absolute path: /tmp/client-file.txt")
        layout.addWidget(self.linux_file_path); layout.addWidget(self.client_file_path)
        layout.addWidget(button("Upload: CLIENT → SERVER", lambda: self.transfer_file("upload")))
        layout.addWidget(button("Download: SERVER → CLIENT", lambda: self.transfer_file("download")))
        note = label("장비록의 여러 CLIENT도 지원합니다. CLIENT→SERVER 다중 업로드 경로에는 {hostname}을 포함하세요. Up to 8 MiB per file. Destination must be new; parent directory must exist. GUI console does not store transferred files.")
        note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(button("GUI ↔ SERVER file transfer window", self.gui_file_dialog))
        self.pages.addWidget(page)

    def refresh_saved_commands(self, select_name=None):
        if not self.require_client(): return
        client = self.client
        def loaded(rows):
            current = select_name or self.saved_commands.currentText()
            self.saved_commands.clear()
            for row in rows: self.saved_commands.addItem(row["name"], row["command"])
            index = self.saved_commands.findText(current)
            if index >= 0: self.saved_commands.setCurrentIndex(index)
        self.work(lambda: client.call("command.saved.list"), loaded)

    def load_saved_command(self):
        command = self.saved_commands.currentData()
        if command is None:
            self.status_line.setText("저장된 명령어를 선택해주세요."); return
        self.command_input.setPlainText(command)
        self.status_line.setText("명령어를 불러왔습니다. 대상을 선택하고 Run command로 실행하세요.")

    def save_command(self):
        if not self.require_client(): return
        command = self.command_input.toPlainText()
        if not command.strip():
            self.status_line.setText("저장할 명령어를 입력해주세요."); return
        name, accepted = QInputDialog.getText(self, "명령어 저장", "이름 (같은 이름으로 저장하면 내용이 갱신됩니다)", text=self.saved_commands.currentText())
        if not accepted or not name.strip(): return
        client = self.client
        def saved(result):
            self.status_line.setText("명령어 저장 완료: " + result["name"])
            self.refresh_saved_commands(result["name"])
        self.work(lambda: client.call("command.saved.save", name=name, command=command), saved)

    def delete_saved_command(self):
        if not self.require_client(): return
        name = self.saved_commands.currentText()
        if not name: return
        client = self.client
        def deleted(result):
            self.status_line.setText("명령어 삭제 완료: " + result["name"])
            self.refresh_saved_commands()
        self.work(lambda: client.call("command.saved.delete", name=name), deleted)

    def gui_file_dialog(self):
        if not self.require_client(): return
        from desktop.file_browser import FileBrowser
        FileBrowser(self.client, self).exec()

    def display_command_results(self, rows, job):
        states = {"completed": "Success", "failed": "Failed", "cancelled": "Cancelled"}
        fill_table(self.command_results_table, [
            [row["hostname"], states.get(row["status"], row["status"]),
             row.get("result", {}).get("exit_code", ""),
             row.get("result", {}).get("stdout", ""),
             row.get("error", row.get("message", row.get("result", {}).get("stderr", "")))] for row in rows])
        self.command_details.setPlainText("Job: " + job["id"] + "\nCommand: " + job.get("options", {}).get("command", "")
                                          + "\nStatus: " + job["status"])
        self.navigate(8)
        self.status_line.setText("Command results: " + str(len(rows)) + " targets / " + job["status"])

    def show_command_detail(self):
        row = self.command_results_table.currentRow()
        if row < 0:
            return
        self.command_details.setPlainText("\n\n".join(
            self.command_results_table.horizontalHeaderItem(c).text() + ":\n" +
            (self.command_results_table.item(row, c).text() if self.command_results_table.item(row, c) else "")
            for c in range(self.command_results_table.columnCount())))

    def run_command(self):
        command = self.command_input.toPlainText(); hosts = self.checked_hosts()
        if not command.strip() or not hosts or not self.require_client():
            self.status_line.setText("Enter a command and select target servers."); return
        if QMessageBox.question(self, "Review command", "Targets: " + self.target_description() + "\n\n" + command) == QMessageBox.Yes:
            if all(r.get("transport")=="agent" for r in self.servers if r["hostname"] in hosts):
                self.start_job("command",options={"command":command});return
            root_password, accepted = QInputDialog.getText(self, "Root transition", "Root password for su fallback (leave blank if sudo works). Kept only for this job:", QLineEdit.EchoMode.Password)
            if accepted:
                self.start_job("command", options={"command": command, "root_password": root_password})

    def transfer_file(self, direction):
        hosts = self.checked_hosts()
        if not hosts or not self.require_client():
            self.status_line.setText("장비 또는 장비록을 선택하세요."); return
        options = {"direction": direction, "server_path": self.linux_file_path.text().strip(),
                   "client_path": self.client_file_path.text().strip()}
        review = "CLIENT: " + hosts[0] + "\n" + direction + "\nSERVER: " + options["server_path"] + "\nCLIENT: " + options["client_path"]
        if QMessageBox.question(self, "Review file transfer", review) == QMessageBox.Yes:
            self.start_job("transfer", options=options)

    def build_accounts(self):
        page = QWidget(); layout = QVBoxLayout(page)
        frame, body = card(); body.addWidget(label("Windows / Linux / AIX accounts", "section"))
        self.account_tabs = QTabWidget()
        targets = QWidget(); targets.setObjectName("accountPage"); target_layout = QVBoxLayout(targets)
        target_layout.addWidget(label("Choose target servers. Selection is shared with Connection map."))
        target_layout.addWidget(button("Select all", lambda: self.check_all(True)))
        target_layout.addWidget(button("Clear selection", lambda: self.check_all(False)))
        self.account_targets = table(["Select", "Server", "IP", "OS"])
        self.account_targets.itemChanged.connect(self.account_target_changed)
        target_layout.addWidget(self.account_targets)
        target_layout.addWidget(button("Query account list", lambda: self.start_job("accounts", options={"action": "list"}), True))
        self.account_tabs.addTab(targets, "1. Target servers")
        operation = QWidget(); operation.setObjectName("accountPage"); operation_layout = QVBoxLayout(operation)
        self.account_tabs.addTab(operation, "2. Account details")
        review = QWidget(); review.setObjectName("accountPage"); review_layout = QVBoxLayout(review)
        self.account_review = QLabel(); self.account_review.setWordWrap(True)
        review_layout.addWidget(self.account_review)
        self.account_run_button=button("Run account operation", self.run_accounts, True); review_layout.addWidget(self.account_run_button)
        review_layout.addStretch()
        self.account_tabs.addTab(review, "3. Review and run")
        self.account_tabs.currentChanged.connect(lambda _: self.update_account_review())
        form = QFormLayout(); self.account_action = QComboBox()
        form.setVerticalSpacing(10)
        for action, title in [("list", "List accounts"), ("create", "Create account"), ("modify", "Update SR and name"), ("groups", "Add supplementary groups"), ("remove_groups", "Remove supplementary groups"), ("primary_group", "Change primary group (one name)"), ("lock", "Lock password login"), ("unlock", "Unlock password login"), ("delete", "Delete account (retain home)")]:
            self.account_action.addItem(title, action)
        self.account_action.addItem("Set password maximum age", "password_age")
        self.account_action.addItem("Set account expiry date", "expiry")
        self.account_action.addItem("Install SSH public key", "public_key")
        form.addRow("Action", self.account_action)
        self.account_fields = {}
        for name, title in [("username", "Username"), ("sr", "SR reference"), ("full_name", "Full name"), ("uid", "UID (optional)"), ("gid", "Existing GID (optional)")]:
            field = QLineEdit(); self.account_fields[name] = field; form.addRow(title, field)
        operation_layout.addLayout(form)
        self.account_fields["groups"] = QLineEdit(); form.addRow("Groups (comma separated)", self.account_fields["groups"])
        self.account_fields["max_days"] = QLineEdit(); form.addRow("Password maximum age (days)", self.account_fields["max_days"])
        self.account_fields["expiry_date"] = QLineEdit(); self.account_fields["expiry_date"].setPlaceholderText("YYYY-MM-DD or never")
        form.addRow("Account expiry", self.account_fields["expiry_date"])
        self.account_fields["public_key"] = QLineEdit()
        self.account_fields["public_key"].setPlaceholderText("ssh-ed25519 AAAA... (public key only)")
        form.addRow("SSH public key", self.account_fields["public_key"])
        def update_fields():
            action = self.account_action.currentData()
            for name, field in self.account_fields.items():
                required = {
                    "username": action != "list", "sr": action in {"create", "modify"},
                    "full_name": action in {"create", "modify"}, "uid": action == "create",
                    "gid": action == "create", "groups": action in {"groups", "remove_groups", "primary_group"},
                    "max_days": action == "password_age", "expiry_date": action == "expiry",
                    "public_key": action == "public_key",
                }[name]
                field.setEnabled(required); form.setRowVisible(field, required)
        self.account_action.currentIndexChanged.connect(update_fields); self.account_action.currentIndexChanged.connect(self.update_windows_query_controls); update_fields()
        note = label("Windows/AIX: accounts are read-only. Linux: New accounts have no password set. Delete retains the home directory. Changes require an encrypted backup.")
        note.setWordWrap(True); operation_layout.addWidget(note); operation_layout.addStretch()
        self.account_table = table(["Server", "Username", "UID / SID", "GID / Groups", "Comment", "Home", "Shell", "Full name", "Enabled", "Account expires", "Password expires", "Last login", "Supplementary groups"])
        results = QWidget(); results_layout = QVBoxLayout(results)
        self.account_result_status = QLabel("Choose CLIENT targets and query the account list.")
        self.account_result_status.setWordWrap(True); results_layout.addWidget(self.account_result_status)
        results_layout.addWidget(button("Download account CSV", self.export_accounts))
        results_layout.addWidget(self.account_table)
        self.account_splitter = QSplitter(Qt.Orientation.Vertical)
        self.account_splitter.addWidget(self.account_tabs); self.account_splitter.addWidget(results)
        self.account_splitter.setChildrenCollapsible(False); self.account_splitter.setSizes([430, 250])
        body.addWidget(self.account_splitter, 1); layout.addWidget(frame); self.pages.addWidget(page)

    def account_target_changed(self, item):
        if item.column() == 0:
            host = row_identity(self.account_targets,item.row())
            for row in range(self.target_table.rowCount()):
                if row_identity(self.target_table,row) == host:
                    self.target_table.item(row,0).setCheckState(item.checkState()); break

    def target_description(self):
        hosts=self.checked_hosts();book=self.active_book()
        return ("장비록 "+book["name"]+" · " if book else "")+str(len(hosts))+"대: "+", ".join(hosts[:10])+(" 외 "+str(len(hosts)-10)+"대" if len(hosts)>10 else "")

    def update_account_review(self):
        self.account_review.setText("Targets: " + self.target_description()
                                   + "\nAction: " + self.account_action.currentText()
                                   + "\nUsername: " + self.account_fields["username"].text().strip())

    def export_accounts(self):
        if not self.account_table.rowCount():
            QMessageBox.information(self, "Account export", "Query the account list first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Download account list", "accounts.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([self.account_table.horizontalHeaderItem(c).text() for c in range(self.account_table.columnCount())])
                for r in range(self.account_table.rowCount()):
                    values = [self.account_table.item(r, c).text() if self.account_table.item(r, c) else "" for c in range(self.account_table.columnCount())]
                    writer.writerow(["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in values])
            self.status_line.setText("Account CSV saved: " + path)
        except OSError:
            QMessageBox.warning(self, "Account export", "Could not save the file. Check the destination and permissions.")

    def run_accounts(self):
        if self.has_readonly_account_patch_targets() and self.account_action.currentData() != "list":return
        options = {name: field.text().strip() for name, field in self.account_fields.items()}
        options["action"] = self.account_action.currentData()
        if options["action"] != "list":
            hosts = self.checked_hosts()
            if not hosts or not self.require_client():
                return
            if QMessageBox.question(self, "Review account operation", f"{options['action']} {options['username']} on: {', '.join(hosts)}?\nLinux will back up each target first.") != QMessageBox.Yes:
                return
        self.start_job("accounts", options=options)

    def display_accounts(self, rows):
        values = []
        for row in rows:
            for account in row.get("result", {}).get("accounts", []):
                values.append([row["hostname"], *[account.get(key, "") for key in ("username", "uid", "gid", "comment", "home", "shell", "full_name", "enabled", "account_expires", "password_expires", "last_logon", "groups")]])
        fill_table(self.account_table, values); self.navigate(4)
        notes = [row.get("result", {}).get("note", "") + " " + row.get("result", {}).get("warnings", "") for row in rows]
        failures = [row["hostname"] + ": " + row.get("error", row.get("message", row["status"]))
                    for row in rows if row["status"] != "completed"]
        self.account_result_status.setText("Accounts: " + str(len(values)) + "\n" + "\n".join(failures + notes)
                                          + ("\nCheck CLIENT login settings (SSH account/password/key); SERVER GUI login is separate." if failures else ""))
        self.status_line.setText(f"Account results: {len(values)} accounts; {sum(row['status'] == 'failed' for row in rows)} failed servers. Details are in Activity.")

    def build_patches(self):
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Windows / Linux / AIX patches", "section"))
        help_text=label("① Connection map에서 CLIENT 선택 → ② 업데이트 조회 → ③ 패키지명(필요시 =버전) 입력 후 계획 미리보기 → ④ 대상·버전·의존성 검토 후 적용. 조회와 계획은 설치하지 않습니다.")
        help_text.setWordWrap(True);body.addWidget(help_text)
        body.addWidget(button("패치 동작·지원 범위 자세히 보기",self.show_patch_help))
        actions = QHBoxLayout()
        actions.addWidget(button("Query Linux updates / Windows KB / AIX filesets", self.query_patches))
        self.patch_packages = QLineEdit(); self.patch_packages.setPlaceholderText("패키지명 또는 패키지명=버전, 공백으로 구분: openssh-server net-tools")
        actions.addWidget(self.patch_packages, 1)
        self.patch_plan_button=button("Preview patch plan", self.plan_patches, True); actions.addWidget(self.patch_plan_button); body.addLayout(actions)
        self.patch_table = table(["Server", "Package / KB", "Installed / Windows date", "Planned version / Windows·AIX status", "Description", "Installed by", "Source", "Type"]); self.patch_table.setMinimumHeight(150); body.addWidget(self.patch_table, 2)
        self.patch_output = QPlainTextEdit(); self.patch_output.setReadOnly(True); self.patch_output.setMinimumHeight(100); body.addWidget(self.patch_output, 1)
        self.patch_plan_id = None
        self.patch_apply = button("Apply reviewed plan", self.apply_patches, True); self.patch_apply.setEnabled(False)
        body.addWidget(self.patch_apply)
        patch_note = label("Windows KB / AIX filesets and interim fixes: query only, no changes. Linux Debian/Ubuntu and RHEL/DNF: reviewed plans and backed-up apply. RHEL requires prepared signed RPMs. No automatic reboot.")
        patch_note.setWordWrap(True); body.addWidget(patch_note)
        layout.addWidget(frame); self.pages.addWidget(page)

    def show_patch_help(self):
        dialog=QDialog(self);dialog.setWindowTitle("패치 실행 안내");dialog.resize(780,580)
        layout=QVBoxLayout(dialog);text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText("""패치는 선택한 Linux CLIENT에서 수행합니다. 관리자 권한이 필요합니다.

1. 업데이트 조회 (Query updates)
현재 CLIENT에 저장된 패키지 메타데이터로 설치 버전과 후보 버전을 조회합니다.
저장소 메타데이터 갱신·다운로드·설치·재부팅을 수행하지 않습니다.
목록이 오래됐거나 비어 있으면 운영 절차에 따라 CLIENT의 저장소/메타데이터를 먼저 준비하세요.

2. 계획 미리보기 (Preview patch plan)
조회 표를 클릭하는 것만으로 적용 대상이 선택되지는 않습니다.
입력 칸에 설치된 패키지명을 공백으로 구분해 입력합니다.
예: openssh-server net-tools / 특정 버전: 패키지명=버전
입력한 패키지와 의존성 변경을 시뮬레이션하고 정확한 버전의 계획을 저장합니다.
신규 패키지를 직접 선택하거나 하위 버전으로 내리는 작업은 거부합니다.
계획 단계는 패키지를 실제 설치하지 않습니다.

3. 검토 후 적용 (Apply reviewed plan)
모든 대상의 계획이 성공하고 적용을 지원할 때 버튼이 활성화됩니다.
CLIENT·버전·의존성·경고를 확인하세요. 계획 유효 시간은 1시간입니다.
적용 전 대상 설정을 백업하고, 계획/현재 상태가 달라지면 중단합니다.
승인된 정확 버전으로 적용하며 자동 재부팅은 하지 않습니다.
패키지 업그레이드 자체가 서비스를 재시작할 수 있으므로 유지보수 시간에 실행하세요.

지원·제약
Debian/Ubuntu: APT 저장소 접근 또는 운영환경의 패키지 제공이 필요합니다.
RHEL/DNF: 서버에 준비한 서명된 RPM과 검토된 로컬 적용 계획을 사용합니다.
실제 RHEL 운영환경 검증은 아직 완료되지 않았습니다. AIX는 설치 파일셋·임시 수정 및 OS 수준 조회만 지원합니다. Windows는 설치된 KB(Get-HotFix/CBS) 조회만 지원합니다.
백업은 설정/진단 보존이며 패키지 버전을 자동으로 되돌리는 전체 시스템 롤백이 아닙니다.
대상별 성공·실패·출력은 결과 표/Activity에서 확인하고 CSV로 저장할 수 있습니다.
07 예약은 수집·자원·보안 점검·백업용이며 패치 자동 적용 예약은 지원하지 않습니다.""")
        layout.addWidget(text);layout.addWidget(button("닫기",dialog.accept));dialog.exec()

    def query_patches(self):
        self.patch_plan_id = None; self.patch_apply.setEnabled(False)
        self.start_job("patches", options={"action": "list"})

    def plan_patches(self):
        if self.has_readonly_account_patch_targets():return
        self.patch_plan_id = None; self.patch_apply.setEnabled(False)
        self.start_job("patches", options={"action": "plan", "packages": self.patch_packages.text().split()})

    def apply_patches(self):
        if self.has_readonly_account_patch_targets():return
        if not self.patch_plan_id:
            return
        plan_id = self.patch_plan_id
        self.patch_apply.setEnabled(False); self.patch_plan_id = None
        self.start_job("patches", options={"action": "apply", "plan_id": plan_id})

    def display_patches(self, rows, job):
        if job.get("options", {}).get("action") == "list":
            self.patch_plan_id = None; self.patch_apply.setEnabled(False)
        values, output = [], []
        for row in rows:
            result = row.get("result", {})
            for package in result.get("packages", []):
                values.append([row["hostname"], package["name"], package["installed"], package["candidate"], package.get("description",""), package.get("installed_by",""), package.get("source",""), package.get("type","")])
            output.append(row["hostname"] + " / " + row["status"] + "\n" + row.get("error", result.get("output", "")))
            if result.get("note"):
                output.append(result["note"])
            if result.get("warnings"):
                output.append("Warnings: " + result["warnings"])
            if result.get("reboot_required"):
                output.append("Reboot required. Restart manually during your maintenance window.")
        fill_table(self.patch_table, values); self.patch_output.setPlainText("\n\n".join(output)); self.navigate(5)
        if job.get("options", {}).get("action") == "plan" and job["status"] == "completed":
            self.patch_plan_id = job["id"]
            self.patch_apply.setEnabled(not self.has_readonly_account_patch_targets() and bool(rows) and all(row.get("result", {}).get("apply_supported", True) for row in rows))

    def build_schedules(self):
        self.schedules = [];self.edit_schedule_id=None;self.edit_schedule_hosts=[]
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Schedules on your Linux server", "section"))
        self.schedule_tabs=QTabWidget();self.schedule_tabs.setStyleSheet("QTabWidget::pane { background:white; border:1px solid #d8e1ee; } QTabWidget QWidget { background:white; color:#20354d; } QTabBar::tab { background:#e8eef8; color:#20354d; padding:8px 16px; } QTabBar::tab:selected { background:white; color:#123967; }");list_page=QWidget();list_body=QVBoxLayout(list_page)
        create_page=QWidget();create_body=QVBoxLayout(create_page)
        self.schedule_tabs.addTab(list_page,"예약 목록");self.schedule_tabs.addTab(create_page,"예약 등록")
        body.addWidget(self.schedule_tabs)
        form = QFormLayout(); self.schedule_kind = QComboBox()
        for kind in ["backup", "connections", "monitoring", "security_audit"]:
            self.schedule_kind.addItem(kind.replace("_", " ").title(), kind)
        self.schedule_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300)); self.schedule_time.setCalendarPopup(True)
        self.schedule_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.schedule_interval = QSpinBox(); self.schedule_interval.setRange(0, 525600); self.schedule_interval.setSuffix(" min (0 = once)")
        self.schedule_mode=QComboBox();self.schedule_mode.addItems(["한 번 / 일정 간격", "Crontab — 분·시·일·월·요일"])
        form.addRow("예약 방식",self.schedule_mode)
        self.cron_fields=[];self.cron_panel=QWidget();cron_layout=QHBoxLayout(self.cron_panel);cron_layout.setContentsMargins(0,0,0,0)
        for title,example in [("분 0–59","0"),("시 0–23","9"),("일 1–31","*"),("월 1–12","*"),("요일 0–7","1-5")]:
            column=QVBoxLayout();column.addWidget(label(title));entry=QLineEdit(example);entry.setMaximumWidth(110)
            column.addWidget(entry);cron_layout.addLayout(column);self.cron_fields.append(entry)
        self.cron_timezone=QLineEdit("Asia/Seoul")
        form.addRow("Crontab",self.cron_panel);form.addRow("Cron 시간대 (IANA)",self.cron_timezone)
        cron_help=label("* 매번 · , 여러 값 · - 범위 · / 간격 | 0 또는 7=일요일, 1=월요일. 예: 0 9 * * 1-5 = 평일 09:00. 일·요일을 모두 제한하면 둘 중 하나가 맞는 날 실행.")
        cron_help.setWordWrap(True)
        def schedule_mode_changed(index):
            use_cron=index==1
            self.cron_panel.setEnabled(use_cron);self.cron_timezone.setEnabled(use_cron)
            self.schedule_time.setEnabled(not use_cron);self.schedule_interval.setEnabled(not use_cron)
        self.schedule_mode.currentIndexChanged.connect(schedule_mode_changed);schedule_mode_changed(0)
        form.setVerticalSpacing(12)
        form.addRow("Operation", self.schedule_kind); form.addRow("First run (this PC local time)", self.schedule_time); form.addRow("Repeat interval", self.schedule_interval)
        create_body.addLayout(form);create_body.addWidget(cron_help)
        persistence_note=label("예약은 Linux SERVER에 암호화 저장됩니다. GUI 종료·PC 종료 후에도 SERVER 서비스가 실행 중이면 동작합니다. 대상은 Connection map 선택을 따릅니다.")
        persistence_note.setWordWrap(True);create_body.addWidget(persistence_note)
        self.schedule_health = label("Refresh schedules to check Linux scheduling status.", "subtitle")
        list_body.addWidget(self.schedule_health)
        self.schedule_replace_hosts=QCheckBox("변경 시 대상을 현재 Connection map 선택으로 교체")
        self.schedule_replace_hosts.setEnabled(False);create_body.addWidget(self.schedule_replace_hosts)
        self.schedule_enabled=QCheckBox("저장 후 예약 사용");self.schedule_enabled.setChecked(True);create_body.addWidget(self.schedule_enabled)
        self.schedule_save_button=button("예약 생성",self.create_schedule,True);create_body.addWidget(self.schedule_save_button)
        self.schedule_table = table(["다음 실행", "작업", "대상 CLIENT", "반복 / Cron (시간대)", "최근 실행", "최근 결과", "예약 상태", "메시지"]); list_body.addWidget(self.schedule_table, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("새 예약",self.new_schedule))
        actions.addWidget(button("선택 예약 변경",self.edit_schedule))
        actions.addWidget(button("예약 목록 조회 / 새로고침", self.load_schedules))
        actions.addWidget(button("Pause selected", lambda: self.change_schedule(False)))
        actions.addWidget(button("Resume selected", lambda: self.change_schedule(True)))
        actions.addWidget(button("Delete selected", lambda: self.change_schedule(delete=True)))
        actions.addWidget(button("예약 목록 CSV 저장",lambda:self.export_widgets(list_page)))
        list_body.addLayout(actions)
        list_body.addWidget(label("Pause/delete stops future runs. Use Activity to cancel pending targets of a started job."))
        create_body.addStretch()
        layout.addWidget(frame); self.pages.addWidget(page)

    def create_schedule(self):
        if not self.require_client():
            return
        client = self.client
        run_at = self.schedule_time.dateTime().toPython().astimezone().isoformat()
        hosts = self.checked_hosts(); kind = self.schedule_kind.currentData(); interval = self.schedule_interval.value() * 60
        options={"run_at":run_at,"interval_seconds":interval}
        if self.schedule_mode.currentIndex()==1:
            options={"cron":" ".join(field.text().strip() for field in self.cron_fields),"cron_timezone":self.cron_timezone.text().strip()}
        book=self.active_book()
        options["equipment_book_id"]=book["id"] if book else None
        options["enabled"]=self.schedule_enabled.isChecked()
        method="schedule.update" if self.edit_schedule_id else "schedule.create"
        if self.edit_schedule_id:
            options["id"]=self.edit_schedule_id;options["enabled"]=self.schedule_enabled.isChecked()
            if not self.schedule_replace_hosts.isChecked():
                hosts=list(self.edit_schedule_hosts);options["equipment_book_id"]=getattr(self,"edit_schedule_book_id",None)
        def saved(item):self.finish_schedule_save()
        self.work(lambda:client.call(method,kind=kind,hosts=hosts,**options),saved)

    def new_schedule(self):
        self.edit_schedule_id=None;self.edit_schedule_hosts=[]
        self.schedule_replace_hosts.setChecked(False);self.schedule_replace_hosts.setEnabled(False)
        self.schedule_enabled.setChecked(True);self.schedule_save_button.setText("예약 생성")
        self.schedule_time.setDateTime(QDateTime.currentDateTime().addSecs(300))
        self.schedule_tabs.setTabText(1,"예약 등록");self.schedule_tabs.setCurrentIndex(1)

    def edit_schedule(self):
        row=self.schedule_table.currentRow()
        if row<0 or row>=len(self.schedules):
            self.status_line.setText("변경할 예약을 목록에서 선택하세요.");return
        item=next(item for item in self.schedules if item["id"]==row_identity(self.schedule_table,row));self.edit_schedule_id=item["id"];self.edit_schedule_hosts=list(item["hosts"]);self.edit_schedule_book_id=item.get("equipment_book_id")
        self.schedule_kind.setCurrentIndex(self.schedule_kind.findData(item["kind"]))
        self.schedule_mode.setCurrentIndex(1 if item.get("cron") else 0)
        if item.get("cron"):
            for entry,value in zip(self.cron_fields,item["cron"].split()):entry.setText(value)
            self.cron_timezone.setText(item.get("cron_timezone") or "UTC")
        self.schedule_interval.setValue(item["interval_seconds"]//60)
        self.schedule_time.setDateTime(QDateTime.fromString(item["next_run"],Qt.DateFormat.ISODate).toLocalTime())
        self.schedule_replace_hosts.setEnabled(True);self.schedule_replace_hosts.setChecked(False)
        self.schedule_enabled.setChecked(item["enabled"]);self.schedule_save_button.setText("예약 변경 저장")
        self.schedule_tabs.setTabText(1,"예약 변경 — "+", ".join(item["hosts"]));self.schedule_tabs.setCurrentIndex(1)

    def finish_schedule_save(self):
        self.edit_schedule_id=None;self.schedule_tabs.setTabText(1,"예약 등록")
        self.schedule_save_button.setText("예약 생성");self.schedule_replace_hosts.setEnabled(False)
        self.schedule_tabs.setCurrentIndex(0);self.load_schedules()

    def load_schedules(self):
        if not self.require_client():
            return
        client = self.client
        def loaded(result):
            schedules, status = result
            self.display_schedules(schedules)
            if status.get("history_errors"):
                message = "Linux history recovery required. Automatic scheduling is blocked."
            elif not status.get("scheduler_running", True):
                message = "Linux scheduler stopped. Inspect Linux storage and restart the service after recovery."
            else:
                message = "Linux scheduler is running. Enabled schedules execute independently of this GUI."
            self.schedule_health.setText(message)
        self.work(lambda: (client.call("schedule.list"), client.call("status")), loaded)

    def display_schedules(self, schedules):
        self.schedules = schedules
        states={"queued":"대기", "running":"실행 중", "completed":"성공", "failed":"실패", "partial":"일부 완료", "cancelled":"취소"}
        values=[]
        for item in schedules:
            repeat=(item["cron"] + " (" + item.get("cron_timezone","UTC") + ")") if item.get("cron") else (str(item["interval_seconds"]//60)+" min" if item["interval_seconds"] else "한 번")
            status="사용" if item["enabled"] else ("완료" if item.get("last_job_id") and not item.get("cron") and not item["interval_seconds"] else "중지")
            values.append([item["next_run"],item["kind"],(item.get("equipment_book_name")+": " if item.get("equipment_book_name") else "")+", ".join(item["hosts"]),repeat,item.get("last_run") or "—",states.get(item.get("last_job_status"),item.get("last_job_status") or "미실행"),status,item["message"]])
        fill_identity_table(self.schedule_table,schedules,values)
        self.schedule_tabs.setTabText(0,"예약 목록 ("+str(len(schedules))+")")

    def change_schedule(self, enabled=None, delete=False):
        row = self.schedule_table.currentRow()
        if row < 0 or row >= len(self.schedules) or not self.require_client():
            return
        schedule_id = row_identity(self.schedule_table,row); client = self.client
        self.work(lambda: client.call("schedule.change", id=schedule_id, enabled=enabled, delete=delete), lambda _: self.load_schedules())

    def cancel_selected_job(self):
        row = self.jobs_table.currentRow()
        if row < 0 or row >= len(self.jobs) or not self.require_client():
            return
        job_id = row_identity(self.jobs_table,row); client = self.client
        self.work(lambda: client.call("job.cancel", id=job_id), lambda _: self.poll())

    def navigate(self, index):
        for metric in self.metric_cards:
            metric.setVisible(index < 4)
        self.pages.setCurrentIndex(index)
        self.pages.updateGeometry()
        if hasattr(self, "fit_timer"): self.fit_timer.start(80)
        if index == 8 and self.client and not self.demo:
            self.refresh_saved_commands()
        titles = ["Infrastructure overview", "Explore your connections", "Protect your configurations", "Every operation, in view", "Accounts — Windows / Linux / AIX", "Patches — Windows / Linux / AIX", "Keep operations on schedule", "Windows / Linux / AIX resources", "Commands and files — Windows / Linux / AIX", "CI 자산 관리 대시보드"]
        self.title.setText(titles[index])
        descriptions = ["Windows · Linux · AIX 통합 관리 콘솔 | 중앙 SERVER에서 작업과 이력을 관리합니다.",
                        "Windows · Linux · AIX 장비의 TCP 연결을 중앙 SERVER에서 수집·보관합니다.",
                        "OS configuration files and account information, encrypted and retained on Linux.",
                        "Follow server-side jobs and inspect their results, even after reconnecting.",
                        "Windows·AIX 계정 조회 · Linux 계정 조회/변경. AIX는 그룹·잠금·만료 원본 값 포함.",
                        "Windows 설치된 KB 조회 · Linux 업데이트 조회/계획/적용. AIX 설치 파일셋·임시 수정 조회 지원.",
                        "Encrypted Linux schedules continue independently of your Windows console.",
                        "Windows CPU·메모리·시스템 디스크 및 Linux/AIX 자원을 조회합니다.", "CLIENT = managed target; SERVER = Linux main server; GUI = this Windows console.", "장비록·개별 장비의 하드웨어, OS, 고객 및 서비스 정보를 관리합니다."]
        self.subtitle.setText(descriptions[index])
        if self.history_errors:
            self.subtitle.setText(f"Linux history recovery required: {len(self.history_errors)} unreadable records. New operations are disabled.")
        for i, item in enumerate(self.nav_buttons):
            item.setChecked(i == index)
        if index == 9:
            self.ci_dashboard.refresh(True)
        if index == 1:
            QTimer.singleShot(50, self.graph.fit_map)
        if index == 6 and self.client:
            self.load_schedules()

    def work(self, fn, done, quiet=False, on_error=None):
        worker = Worker(fn); self.workers.add(worker)
        epoch = self.epoch
        def success(result):
            self.workers.discard(worker)
            if epoch == self.epoch:
                done(result)
        def failure(message):
            self.workers.discard(worker)
            if epoch != self.epoch:
                return
            self.poll_busy = False
            if on_error:
                on_error()
            self.status_line.setText("Request failed: " + message[:160])
            if not quiet:
                QMessageBox.warning(self, "Operation could not finish", message)
        worker.signals.done.connect(success); worker.signals.error.connect(failure)
        QThreadPool.globalInstance().start(worker)

    def connect_server(self):
        if self.demo:
            QMessageBox.information(self, "Visual demo", "Restart without --demo to connect to a real Linux main server."); return
        dialog = ConnectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.settings()
        if not settings.host or not settings.username or not settings.password:
            QMessageBox.warning(self, "Connection details", "Server IP, ID and password are required."); return
        client = ServerClient(settings)
        self.connect_to(client)

    def attach_client(self, client, status):
        settings = client.settings
        self.epoch += 1; self.client = client; self.loaded_job = None; self.active_job = None
        self.submission_pending = False
        self.poll_busy = False
        self.clear_session_views()
        self.server_badge.setText(f"{settings.host}\nTLS : {settings.port}")
        role=status.get("role","admin");self.user_role=role
        self.connection_badge.setText("CONNECTED / TLS / " + role.upper())
        self.command_run_button.setEnabled(role == "admin")
        self.agent_setup_action.setEnabled(role == "admin")
        self.subtitle.setText(f"Execution: Linux main server   |   Data: {status['data_directory']}")
        self.history_errors = status.get("history_errors", [])
        self.subtitle.setToolTip("")
        if status.get("history_errors"):
            self.subtitle.setText("Linux history recovery required: " + str(len(status["history_errors"])) +
                                  " unreadable records. Existing results remain readable; new operations are disabled.")
            self.subtitle.setToolTip("Linux DATA/jobs recovery required:\n" +
                                     "\n".join(f"{item['file']}: {item['error']}" for item in self.history_errors) +
                                     "\nPreserve these files and restore the original key/history on Linux, then restart the service.\nPaused schedules require review before resuming.")
        self.status_line.setText("Connected. All operational work executes on Linux."); self.reload()

    def connect_to(self, client):
        self.status_line.setText("Connecting to Linux main server...")
        def handshake():
            status=client.call("status");status["role"]=client.call("session.info")["role"];return status
        self.work(handshake, lambda status: self.attach_client(client, status))

    def disconnect_server(self):
        if self.demo:
            return
        self.epoch += 1; self.client = None; self.active_job = None; self.poll_busy = False
        self.history_errors = []; self.subtitle.setToolTip("")
        self.submission_pending = False
        self.clear_session_views()
        self.server_badge.setText("Not connected"); self.connection_badge.setText("OFFLINE")
        self.subtitle.setText("Windows · Linux · AIX 통합 관리 콘솔 | 중앙 SERVER에서 작업과 이력을 관리합니다.")
        self.status_line.setText("Disconnected. Jobs already submitted continue on Linux.")

    def clear_session_views(self):
        self.agent_inventory_busy=False
        self.ci_dashboard.clear()
        self.equipment_books=[];self.book_selector.blockSignals(True);self.book_selector.clear();self.book_selector.addItem("개별 장비 선택",None);self.book_selector.blockSignals(False)
        self.saved_commands.clear()
        self.job_history = {}; self.job_history_offset = 100
        self.backup_history = {}; self.backup_history_offset = 0
        self.resource_auto.setChecked(False); self.resource_loaded_job = None
        self.resource_table.setRowCount(0); self.resource_updated.setText("No resource snapshot loaded")
        self.connection_cache={}; self.connection_cache_loading=False
        self.connection_results = []; self.jobs = []
        self.set_inventory([]); self.update_map(); self.set_jobs([])
        self.metric_values[2].setText("—"); self.progress.setValue(0)
        self.account_table.setRowCount(0)
        self.account_result_status.setText("Choose CLIENT targets and query the account list.")
        self.backup_root_password.clear()
        self.command_results_table.setRowCount(0); self.command_details.clear()
        self.patch_table.setRowCount(0)
        self.patch_output.clear()
        self.patch_plan_id = None
        self.patch_apply.setEnabled(False)
        self.schedules = []
        self.schedule_table.setRowCount(0)
        self.schedule_health.setText("Refresh schedules to check Linux scheduling status.")

    def require_client(self):
        if not self.client:
            QMessageBox.information(self, "Linux connection required", "Connect to the Linux main server first. Demo mode never runs operations.")
            return False
        return True

    def reload(self):
        if not self.require_client():
            return
        client = self.client
        def loaded_inventory(rows):
            self.set_inventory(rows);self.refresh_books();self.restore_connection_cache()
        self.work(lambda: client.call("inventory.list"), loaded_inventory)
        self.poll()

    def set_inventory(self, servers):
        def identity(server):
            return tuple(server.get(field, "default" if field == "profile" else "") for field in ("hostname", "ip", "os", "profile"))
        initial = not self.servers
        checked = set(self.checked_hosts())
        selected = {identity(server) for server in self.servers if server["hostname"] in checked}
        self.servers = servers; self.metric_values[0].setText(str(len(servers)))
        fill_table(self.inventory_table, [[r["hostname"], r["ip"], r["os"], ("Windows agent / "+r.get("agent_status","unknown")) if r.get("transport")=="agent" else "Linux main server / SSH"] for r in servers])
        self.target_table.blockSignals(True); sorting = self.target_table.isSortingEnabled(); self.target_table.setSortingEnabled(False); self.target_table.setRowCount(len(servers))
        for row, server in enumerate(servers):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setData(Qt.ItemDataRole.UserRole,server["hostname"])
            check.setCheckState(Qt.CheckState.Checked if initial or identity(server) in selected else Qt.CheckState.Unchecked)
            self.target_table.setItem(row, 0, check)
            item = QTableWidgetItem(server["hostname"] + "\n" + server["ip"])
            item.setToolTip(server["os"]); self.target_table.setItem(row, 1, item); self.target_table.setRowHeight(row, 60)
        self.target_table.setSortingEnabled(sorting); self.target_table.blockSignals(False)
        self.select_all.blockSignals(True); self.select_all.setChecked(True); self.select_all.blockSignals(False)
        self.apply_book_selection(); self.filter_servers(self.server_search.text())

    def active_book(self):
        identity=self.book_selector.currentData()
        return next((book for book in self.equipment_books if book["id"]==identity),None)

    def refresh_books(self,select=None):
        if not self.client or self.demo:return
        client=self.client;previous=select or self.book_selector.currentData()
        def loaded(rows):
            self.equipment_books=rows;self.book_selector.blockSignals(True);self.book_selector.clear();self.book_selector.addItem("개별 장비 선택",None)
            for book in rows:self.book_selector.addItem(book["name"]+" ("+str(len(book["hosts"]))+"대)",book["id"])
            index=self.book_selector.findData(previous)
            self.book_selector.setCurrentIndex(max(0,index));self.book_selector.blockSignals(False)
            if previous and index<0:self.check_all(False)
            self.apply_book_selection()
        self.work(lambda:client.call("equipment.book.list"),loaded)

    def manage_books(self):
        if not self.require_client():return
        from desktop.equipment_books import EquipmentBooks
        dialog=EquipmentBooks(self.client,self.servers,self,readonly=getattr(self,"user_role","admin")!="admin")
        dialog.exec();self.refresh_books(dialog.chosen)

    def apply_book_selection(self,*_):
        book=self.active_book();self.target_table.blockSignals(True)
        for row in range(self.target_table.rowCount()):
            host=row_identity(self.target_table,row)
            check=self.target_table.item(row,0)
            check.setFlags(Qt.ItemFlag.ItemIsEnabled if book else Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            if book:check.setCheckState(Qt.CheckState.Checked if host in book["hosts"] else Qt.CheckState.Unchecked)
        self.target_table.blockSignals(False);self.select_all.setEnabled(not book);self.selection_changed()

    def checked_hosts(self):
        book=self.active_book()
        if book:return list(book["hosts"])
        return [row_identity(self.target_table,row) for row in range(self.target_table.rowCount())
                if self.target_table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def has_windows_targets(self):
        names=set(self.checked_hosts())
        return any(r["hostname"] in names and "win" in r.get("os","").lower() for r in self.servers)

    def has_readonly_account_patch_targets(self):
        names=set(self.checked_hosts())
        return any(r["hostname"] in names and any(os in r.get("os", "").lower() for os in ("win","aix")) for r in self.servers)

    def update_windows_query_controls(self, *_):
        windows=self.has_readonly_account_patch_targets()
        if hasattr(self,"account_run_button"):
            self.account_run_button.setEnabled(not windows or self.account_action.currentData()=="list")
        if hasattr(self,"patch_plan_button"):
            self.patch_plan_button.setEnabled(not windows); self.patch_packages.setEnabled(not windows)
            if windows:self.patch_apply.setEnabled(False)

    def selection_changed(self, *_):
        self.update_windows_query_controls()
        hosts = self.checked_hosts(); self.metric_values[1].setText(str(len(hosts)))
        if hasattr(self, "command_targets"):
            self.command_targets.setText("Selected targets: " + self.target_description())
        if hasattr(self, "account_targets"):
            self.account_targets.blockSignals(True)
            sorting = self.account_targets.isSortingEnabled(); self.account_targets.setSortingEnabled(False)
            populate(self.account_targets, [["", r["hostname"], r["ip"], r["os"]] for r in self.servers], [r["hostname"] for r in self.servers])
            for row, server in enumerate(self.servers):
                check = self.account_targets.item(row, 0)
                check.setFlags(Qt.ItemFlag.ItemIsEnabled if self.active_book() else Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked if server["hostname"] in hosts else Qt.CheckState.Unchecked)
            self.account_targets.setSortingEnabled(sorting); self.account_targets.blockSignals(False)
            self.update_account_review()
        self.select_all.blockSignals(True); self.select_all.setChecked(bool(self.servers) and len(hosts) == len(self.servers)); self.select_all.blockSignals(False)
        if hasattr(self,"connection_page"):self.show_selected_connections()

    def check_all(self, checked):
        if self.active_book():return
        self.target_table.blockSignals(True)
        for row in range(self.target_table.rowCount()):
            self.target_table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.target_table.blockSignals(False); self.selection_changed()

    def filter_servers(self, query):
        indexed = {r["hostname"]:r for r in self.servers}
        for row in range(self.target_table.rowCount()):
            server = indexed[row_identity(self.target_table,row)]
            self.target_table.setRowHidden(row, query.casefold() not in (server["hostname"] + server["ip"]).casefold())

    def edit_inventory(self):
        if not self.require_client():
            return
        client = self.client
        def loaded(profiles):
            dialog = InventoryDialog(self, self.servers, profiles)
            if dialog.exec() == QDialog.DialogCode.Accepted and self.client is client:
                rows = dialog.rows()
                self.work(lambda: client.call("inventory.save", servers=rows), lambda _: self.reload())
        self.work(lambda: client.call("ssh.profiles"), loaded)

    def export_inventory_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Download CLIENT inventory", "clients.xlsx", "Excel (*.xlsx)")
        if path:
            from desktop.inventory_excel import save
            try:
                save(path if path.lower().endswith(".xlsx") else path + ".xlsx", self.servers)
            except OSError:
                QMessageBox.warning(self, "Export failed", "Could not save the workbook.")

    def deploy_server_key(self):
        if not self.require_client():return
        from desktop.key_targets import PublicKeyTargetsDialog
        dialog=PublicKeyTargetsDialog(self,self.servers,self.checked_hosts())
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.start_job("deploy_key",hosts_override=dialog.selected_hosts())

    def import_csv(self):
        if not self.require_client():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import hostname,ip,os CSV (replaces inventory)", "", "Inventory (*.xlsx *.csv *.txt)")
        if path:
            try:
                from desktop.inventory_excel import read_csv
                content = read_csv(path) if path.lower().endswith(".xlsx") else Path(path).read_text(encoding="utf-8-sig")
            except Exception as exc:
                QMessageBox.warning(self, "Import failed", str(exc)); return
            client = self.client
            self.work(lambda: client.call("inventory.import", csv=content), lambda _: self.reload())

    def start_job(self, kind, all_hosts=False, options=None, hosts_override=None):
        if not self.require_client():
            return
        if self.history_errors:
            QMessageBox.information(self, "Linux history recovery required", self.subtitle.toolTip())
            return
        if self.submission_pending:
            self.status_line.setText("Waiting for Linux to acknowledge the submitted operation.")
            return
        book=self.active_book()
        hosts = [row["hostname"] for row in self.servers] if all_hosts and not book else self.checked_hosts()
        if hosts_override is not None:
            hosts = hosts_override; book = None
        if not hosts:
            QMessageBox.information(self, "Select targets", "Select at least one server in Connection map."); return
        client = self.client
        self.submission_pending = True
        def failed():
            self.submission_pending = False
        def started(job):
            self.submission_pending = False
            self.active_job = job["id"]; self.loaded_job = None
            if kind in {"backup","backup_compare"}:self.backup_root_password.clear()
            if kind == "command":
                fill_table(self.command_results_table, [[host, "Queued", "", "", ""] for host in hosts])
                self.command_details.setPlainText("Command submitted. Waiting for target results.")
            self.status_line.setText(f"{kind}: submitted to Linux for {len(hosts)} servers."); self.poll()
        self.work(lambda: client.call("job.start", kind=kind, hosts=hosts, options=options or {},equipment_book_id=book["id"] if book else None), started, on_error=failed)

    def poll(self):
        if not self.client or self.poll_busy:
            return
        self.poll_busy = True; client = self.client
        self.work(lambda: client.call("job.list"), self.set_jobs, quiet=True)

    def load_backup_history(self, refresh=False):
        if not self.require_client():
            return
        client = self.client
        offset = 0 if refresh else self.backup_history_offset
        def loaded(jobs):
            self.backup_history_offset = offset + len(jobs)
            self.display_backup_history(jobs)
            self.status_line.setText(f"Backup history: {len(self.backup_history)} records loaded." +
                                     (" No older backups in this page." if not jobs else ""))
        self.work(lambda: client.call("job.list", kind="backup", offset=offset), loaded)

    def display_backup_history(self, jobs):
        self.backup_history.update({job["id"]: job for job in jobs})
        self.backup_jobs = sorted(self.backup_history.values(), key=lambda job: (job["created_at"], job["id"]), reverse=True)
        fill_identity_table(self.backup_table, self.backup_jobs, [[j["created_at"], j["status"], f"{j['done']}/{j['total']}", j["id"][:12]] for j in self.backup_jobs])

    def load_job_history(self):
        if not self.require_client():
            return
        client = self.client; offset = self.job_history_offset
        def loaded(jobs):
            self.job_history_offset = offset + len(jobs)
            self.set_jobs(jobs)
            self.status_line.setText(f"Operation history: {len(self.job_history)} records loaded." +
                                     (" No older operations in this page." if not jobs else ""))
        self.work(lambda: client.call("job.list", offset=offset), loaded)

    def set_jobs(self, jobs):
        self.poll_busy = False
        self.job_history.update({job["id"]: job for job in jobs})
        jobs = sorted(self.job_history.values(), key=lambda job: (job["created_at"], job["id"]), reverse=True)
        self.jobs = jobs
        self.timer.setInterval(3000 if any(j["status"] in {"queued","running"} for j in jobs) else 15000)
        fill_identity_table(self.jobs_table, jobs, [[j["created_at"], j["kind"], j["status"], f"{j['done']}/{j['total']}", j["id"][:12], j.get("message", "")] for j in jobs])
        self.display_backup_history([j for j in jobs if j["kind"] == "backup"])
        resource = next((job for job in jobs if job["kind"] == "monitoring" and job["status"] not in {"queued", "running"}), None)
        if resource and resource["id"] != self.resource_loaded_job and self.client:
            self.resource_loaded_job = resource["id"]; client = self.client
            def resource_failed():
                if self.resource_loaded_job == resource["id"]:
                    self.resource_loaded_job = None
            self.work(lambda: client.results(resource["id"],self.checked_hosts()), lambda rows: self.display_resources(rows, resource.get("finished_at", resource["created_at"])), quiet=True, on_error=resource_failed)
        active = next((j for j in jobs if j["id"] == self.active_job), None)
        if active:
            self.progress.setValue(int(100 * active["done"] / max(1, active["total"])))
            self.status_line.setText(f"{active['kind']} / {active['status']} / {active.get('message', '')}")
            if active["status"] not in {"queued", "running"} and self.loaded_job != active["id"]:
                self.loaded_job = active["id"]
                def result_failed():
                    if self.loaded_job == active["id"]:
                        self.loaded_job = None
                if active["kind"] == "ci_inventory":
                    self.ci_dashboard.refresh()
                elif active["kind"] == "connections":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), self.display_connections, quiet=True, on_error=result_failed)
                elif active["kind"] == "command":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), lambda rows: self.display_command_results(rows, active), quiet=True, on_error=result_failed)
                elif active["kind"] == "backup_compare":
                    client=self.client
                    self.work(lambda:client.results(active["id"]),lambda rows:self.display_backup_comparison(rows,active),quiet=True,on_error=result_failed)
                elif active["kind"] == "accounts":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), self.display_accounts, quiet=True, on_error=result_failed)
                elif active["kind"] == "patches":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), lambda rows: self.display_patches(rows, active), quiet=True, on_error=result_failed)

    def restore_connection_cache(self):
        if not self.client or self.connection_cache_loading:return
        self.connection_cache_loading=True;client=self.client
        def load():
            rows=[];offset=0
            while True:
                if client is not self.client:return rows
                page=client.call("connections.cached",offset=offset);rows.extend(page["items"])
                offset+=len(page["items"])
                if offset>=page["total"] or not page["items"]:return rows
        def loaded(rows):
            self.connection_cache_loading=False
            self.remember_connections(rows);self.show_selected_connections()
        self.work(load,loaded,quiet=True,on_error=lambda:setattr(self,"connection_cache_loading",False))

    def remember_connections(self,rows):
        for row in rows:
            key=tuple(row.get(k,"") for k in ("hostname","ip","os"))
            old=self.connection_cache.get(key)
            if old is None or row.get("observed_at","")>=old.get("observed_at",""):self.connection_cache[key]=row

    def show_selected_connections(self):
        hosts=set(self.checked_hosts());rows=[]
        for host in self.servers:
            if host['hostname'] not in hosts:continue
            key=tuple(host.get(k,"") for k in ("hostname","ip","os"))
            rows.append(self.connection_cache.get(key,{**host,"status":"not_collected"}))
        self.connection_results=rows
        self.metric_values[2].setText(str(sum(len(r.get("result",{}).get("connections",[])) for r in rows)))
        self.update_map()

    def display_connections(self, rows):
        self.remember_connections(rows)
        self.connection_results = rows
        if self.servers:self.show_selected_connections()
        total = sum(len(row.get("result", {}).get("connections", [])) for row in rows)
        self.metric_values[2].setText(str(sum(len(r.get("result",{}).get("connections",[])) for r in self.connection_results))); self.update_map(); self.navigate(1)
        failures = sum(row["status"] == "failed" for row in rows)
        cancelled = sum(row["status"] == "cancelled" for row in rows)
        empty = sum(row["status"] == "completed" and not row.get("result", {}).get("connections")
                    and not row.get("result", {}).get("truncated") for row in rows)
        warnings = sum(bool(row.get("result", {}).get("warning")) for row in rows)
        truncated = any(row.get("result", {}).get("truncated") for row in rows)
        self.status_line.setText(f"Snapshot loaded: {total} established connections; {empty} servers with no connections, {failures} failed, {cancelled} cancelled." +
                                 (f" {warnings} servers reported collection warnings; hover over map notices for details." if warnings else "") +
                                 (" Large results limited to 5,000 connections per host." if truncated else ""))

    def update_map(self, *_):
        self.map_filter_timer.stop()
        self.map_generation+=1; generation=self.map_generation
        snapshot=self.connection_results; query=self.peer_search.text().strip()
        def loaded(rows):
            if generation!=self.map_generation:return
            self.filtered_connections=rows
            count=sum(len(row.get("result",{}).get("connections",[])) for row in rows)
            self.map_page.blockSignals(True); self.map_page.setRange(1,max(1,(len(rows)+9)//10)); self.map_page.setValue(1); self.map_page.blockSignals(False)
            self.connection_page.blockSignals(True); self.connection_page.setRange(1,max(1,(count+199)//200)); self.connection_page.setValue(1); self.connection_page.blockSignals(False)
            self.connection_count.setText(f"조회 {len(rows):,}대 / {count:,}건 · CSV는 검색 결과 전체 저장 · 표 정렬은 현재 페이지")
            self.render_connection_pages(); self.render_connection_table()
        if not query:loaded(snapshot)
        else:self.work(lambda:filter_snapshot(snapshot,query),loaded,quiet=True)

    def render_connection_pages(self, *_):
        start=(self.map_page.value()-1)*10
        self.graph.set_results(self.filtered_connections[start:start+10], self.peer_search.text())

    def render_connection_table(self, *_):
        fill_table(self.connection_table,table_page(self.filtered_connections,self.connection_page.value()))

    def display_backup_comparison(self,rows,job):
        from desktop.backup_compare import ComparisonDialog
        ComparisonDialog(rows,job,self).exec()

    def show_job(self, job_id):
        if not self.require_client():
            return
        client = self.client
        def show(rows):
            job = next((item for item in self.jobs if item["id"] == job_id), self.backup_history.get(job_id, {}))
            if job.get("kind") == "command":
                self.display_command_results(rows, job); return
            if job.get("kind") == "connections":
                self.display_connections(rows)
                if job.get("status") != "completed":
                    self.status_line.setText(f"{job.get('status', 'unknown')}: {len(rows)}/{job.get('total', '?')} target results available. " + job.get("message", ""))
                return
            if job.get("kind") == "backup_compare":
                self.display_backup_comparison(rows,job);return
            if job.get("kind") == "backup":
                self.show_backup_results(rows, job); return
            if job.get("kind") == "monitoring":
                self.display_resources(rows, job.get("finished_at", job.get("created_at", ""))); self.navigate(7); return
            if job.get("kind") == "security_audit":
                from desktop.security import audit_rows
                dialog = QDialog(self); dialog.setWindowTitle("Linux security observations"); dialog.resize(980, 560)
                layout = QVBoxLayout(dialog)
                layout.addWidget(label("Review flags are guidance. No security policy has been changed."))
                findings = table(["Server", "Setting", "Observed value", "Assessment"])
                fill_table(findings, audit_rows(rows)); layout.addWidget(findings)
                layout.addWidget(button("Save results CSV", lambda: self.export_widgets(dialog))); layout.addWidget(button("Close", dialog.accept)); dialog.exec(); return
            if job.get("kind") == "security_plan":
                self.security_plan_dialog(rows, job_id, job.get("status") == "completed").exec(); return
            dialog = QDialog(self); dialog.setWindowTitle("Linux job results"); dialog.resize(880, 620)
            layout = QVBoxLayout(dialog); text = QPlainTextEdit(); text.setReadOnly(True)
            text.setPlainText(json.dumps({"job": job, "results": rows}, ensure_ascii=False, indent=2)); layout.addWidget(text)
            layout.addWidget(button("Save results CSV", lambda: self.export_widgets(dialog))); layout.addWidget(button("Close", dialog.accept)); dialog.exec()
        self.work(lambda: client.results(job_id), show)

    def security_plan_dialog(self, rows, job_id, completed=False):
        from desktop.security import plan_rows
        dialog = QDialog(self); dialog.setWindowTitle("SSH policy change plan"); dialog.resize(1080, 620)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Review SSH policy changes", "section"))
        layout.addWidget(label("Linux backs up each target before applying changes. A failed reconnect triggers recovery.", "subtitle"))
        findings = table(["Server", "Setting", "Current", "Planned", "Status / reason"])
        fill_table(findings, plan_rows(rows)); layout.addWidget(findings)
        targets_match = set(self.checked_hosts()) == {row["hostname"] for row in rows}
        supported = bool(rows) and all(row.get("status") == "completed" and row.get("result", {}).get("plan", {}).get("status") in {"no_changes", "action_required"} for row in rows)
        layout.addWidget(label("Select exactly the servers listed in this plan before applying." if not targets_match else "Plan targets match the selected servers. Plans expire after one hour."))
        apply_button = button("Apply reviewed SSH plan", lambda: (dialog.accept(), self.start_job("security_apply", options={"plan_id": job_id})), True)
        apply_button.setEnabled(completed and supported and targets_match and not self.demo)
        layout.addWidget(apply_button)
        layout.addWidget(button("Save results CSV", lambda: self.export_widgets(dialog))); layout.addWidget(button("Close", dialog.accept))
        return dialog

    def show_backup_results(self, rows, job=None):
        self.backup_results_dialog(rows, job).exec()

    def backup_results_dialog(self, rows, job=None):
        dialog = QDialog(self); dialog.setWindowTitle("Backup artifacts on Linux"); dialog.resize(1060, 720)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Browse encrypted backups", "section"))
        if job:
            layout.addWidget(label(f"Job status: {job.get('status', 'unknown')} / {len(rows)} of {job.get('total', '?')} targets have saved results", "subtitle"))
            if job.get("status") != "completed" and job.get("message"):
                note = label(job["message"], "subtitle"); note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(label("Double-click an artifact to preview text or list archive files. Decryption runs on Linux.", "subtitle"))
        tree = QTreeWidget(); tree.setHeaderLabels(["Server / artifact", "Status", "Size", "Linux storage path"])
        tree.setSortingEnabled(True); tree.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        tree.setStyleSheet("QTreeWidget { background: white; color: #20354d; alternate-background-color: #f4f7fb; } QTreeWidget::item:selected { background: #dbeafe; color: #172d48; }")
        tree.setAlternatingRowColors(True)
        tree.setColumnWidth(0, 260); tree.setColumnWidth(1, 100); tree.setColumnWidth(2, 90)
        for row in rows:
            result = row.get("result", {})
            parent = SortTreeItem([row["hostname"], row["status"], "", result.get("directory", row.get("error", ""))])
            tree.addTopLevelItem(parent)
            for artifact in result.get("artifacts", []):
                path = artifact.get("path", "")
                item = SortTreeItem([artifact["name"], artifact["status"],
                                        f"{artifact.get('size', 0):,} B", path or artifact.get("error", "")])
                item.setData(0, Qt.ItemDataRole.UserRole, path); parent.addChild(item)
                details = []
                if "exit_code" in artifact:
                    details.append(f"Command exit code: {artifact['exit_code']}")
                if artifact.get("error"):
                    details.append("Collection error: " + artifact["error"])
                details.extend(artifact.get("warnings", []))
                details.extend("Command error: " + error for error in artifact.get("errors", []))
                if artifact.get("errors_truncated"):
                    details.append("Error summary limited; open command details for full diagnostics")
                for detail in details:
                    child = SortTreeItem([detail, "", "", ""])
                    child.setToolTip(0, detail)
                    item.addChild(child)
                if path:
                    metadata = path.rsplit("/", 1)[0] + "/" + artifact["name"] + ".metadata.json.enc"
                    child = SortTreeItem(["Command details and diagnostic output", "", "", metadata])
                    child.setData(0, Qt.ItemDataRole.UserRole, metadata)
                    item.addChild(child)
                if artifact["status"] != "completed":
                    item.setExpanded(True)
                    item.setForeground(1, QColor("#b45309"))
            parent.setExpanded(True)
        layout.addWidget(tree, 2)
        preview = QPlainTextEdit(); preview.setReadOnly(True)
        preview.setPlaceholderText("Select an artifact. Archive listings show paths, permissions and sizes without extracting files.")
        layout.addWidget(preview, 1)
        request_number = [0]
        dialog.finished.connect(lambda _: request_number.__setitem__(0, request_number[0] + 1))
        def view(item, _):
            request_number[0] += 1
            requested = request_number[0]
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if not path:
                preview.setPlainText(item.text(0))
                return
            if not path.endswith((".txt.enc", ".json.enc", ".tar.enc")):
                preview.setPlainText("Binary archive: use scripts/decrypt_artifact.py on the Linux server."); return
            client = self.client
            if client is None:
                return
            preview.setPlainText("Loading preview from Linux...")
            def loaded(response):
                if requested == request_number[0]:
                    preview.setPlainText(response["text"] + ("\n\n[Preview limited to 64 KiB]" if response["truncated"] else ""))
            method = "backup.contents" if path.endswith(".tar.enc") else "backup.preview"
            self.work(lambda: client.call(method, path=path), loaded)
        tree.itemDoubleClicked.connect(view)
        layout.addWidget(button("Save results CSV", lambda: self.export_widgets(dialog))); layout.addWidget(button("Close", dialog.accept))
        return dialog

    def load_demo(self):
        from desktop.demo import SERVERS, connection_rows
        self.set_inventory(SERVERS)
        self.target_table.item(3, 0).setCheckState(Qt.CheckState.Unchecked)
        self.server_badge.setText("sm-main.example.internal\nTLS : 7443 / Preview")
        self.connection_badge.setText("DEMO  /  SYNTHETIC DATA")
        self.subtitle.setText("Windows · Linux · AIX 장비의 TCP 연결을 중앙 SERVER에서 수집·보관합니다.")
        self.display_connections(connection_rows())
        self.display_resources([
            {"hostname": "app-linux-01", "status": "completed", "result": {"load_average": [0.42, 0.31, 0.28], "memory_mb": {"used": 5930, "total": 16384}, "root_filesystem": {"capacity": "47%"}, "uptime": "up 12 days, 3 hours"}},
            {"hostname": "db-linux-01", "status": "completed", "result": {"load_average": [1.81, 1.64, 1.52], "memory_mb": {"used": 29492, "total": 32768}, "root_filesystem": {"capacity": "92%"}, "uptime": "up 31 days, 7 hours"}},
        ])
        fill_table(self.account_table, [["app-linux-01", "ops_example", "2001", "2001", "SR2026-2026-10-08-Example Operator", "/home/ops_example", "/bin/bash"]])
        self.account_action.setCurrentIndex(1)
        for name, value in {"username": "ops_example", "sr": "SR2026", "full_name": "Example Operator", "uid": "2001"}.items():
            self.account_fields[name].setText(value)
        fill_table(self.patch_table, [["web-prod-01", "openssh-server:x86_64", "8.7p1-38.el9_4.1", "8.7p1-38.el9_4.4"],
                                      ["app-prod-02", "openssh-server", "1:9.6p1-3ubuntu13.10", "1:9.6p1-3ubuntu13.14"]])
        self.patch_output.setPlainText("SYNTHETIC PATCH PLAN / RHEL AND UBUNTU\n2 selected packages upgraded, 0 unrelated removals.\nRHEL: prepared signed RPMs required; no download or automatic reboot.\nLinux backs up each target before applying a reviewed plan.")
        self.display_schedules([{"id": "demo-schedule", "next_run": "2026-10-09T01:00:00+09:00", "kind": "backup", "hosts": ["app-linux-01", "db-linux-01"], "interval_seconds": 86400, "enabled": True, "message": "Waiting on Linux"}])
        self.schedule_time.setDateTime(QDateTime.fromString("2026-10-09T01:00:00", Qt.DateFormat.ISODate))
        self.schedule_interval.setValue(1440)
        self.set_jobs([{"id": "demo-backup-001", "kind": "backup", "status": "partial", "total": 4,
                        "done": 4, "failed": 0, "partial": 1, "created_at": "2026-10-08T18:30:00+09:00"}])
        self.status_line.setText("VISUAL MOCKUP  /  Synthetic sample data. No server connection or operational task is running.")


def main():
    parser = argparse.ArgumentParser(description="SM Automation native desktop console")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--page", choices=["overview", "connections", "backups", "activity", "accounts", "patches", "schedules", "resources", "security", "backup-details", "inventory"], default="connections")
    parser.add_argument("--mockup", type=Path, help="Render synthetic demo to PNG without connecting to any server")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    if sys.platform == "win32":
        for filename in ("segoeui.ttf", "segoeuib.ttf", "malgun.ttf"):
            font_file = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font_file.exists():
                QFontDatabase.addApplicationFont(str(font_file))
    app.setFont(QFont("Segoe UI", 10)); app.setStyle("Fusion"); app.setPalette(light_palette()); app.setStyleSheet(STYLE)
    window = Console(demo=args.demo or bool(args.mockup)); window.show()
    if args.demo or args.mockup:
        window.navigate(["overview", "connections", "backups", "activity", "accounts", "patches", "schedules", "resources"].index(args.page) if args.page not in {"security", "backup-details", "inventory"} else 3)
    preview = window
    if args.page == "inventory" and (args.demo or args.mockup):
        preview = InventoryDialog(window, [
            {"hostname": "app-rhel-01", "ip": "192.0.2.11", "os": "RHEL 9", "profile": "unix-admin"},
            {"hostname": "app-ubuntu-01", "ip": "192.0.2.21", "os": "Ubuntu 24.04", "profile": "default"},
            {"hostname": "app-windows-01", "ip": "192.0.2.31", "os": "Windows 2022", "profile": "windows-admin"},
            {"hostname": "legacy-aix-01", "ip": "192.0.2.41", "os": "AIX 7.3", "profile": "old-profile"},
        ], ["default", "unix-admin", "windows-admin"])
        preview.show()
    if args.page == "backup-details" and (args.demo or args.mockup):
        prefix = "2026-10-09/app-rhel-01/synthetic-run"
        preview = window.backup_results_dialog([{
            "hostname": "app-rhel-01", "status": "partial", "result": {"directory": "BACKUP/" + prefix,
            "artifacts": [
                {"name": "configuration_files", "status": "completed", "size": 204800,
                 "path": prefix + "/configuration_files.tar.enc", "exit_code": 0,
                 "warnings": ["Missing optional path: /etc/netplan"]},
                {"name": "network", "status": "partial", "size": 4096,
                 "path": prefix + "/network.txt.enc", "exit_code": 1,
                 "errors": ["Synthetic example: network command returned permission denied"]},
                {"name": "account_expiry_chage", "status": "failed",
                 "error": "Synthetic example: remote command timed out"},
            ]}}], {"status": "interrupted", "total": 4,
                    "message": "Synthetic example: Linux restarted; inspect saved artifacts before retrying."})
        preview.show()
    if args.page == "security" and (args.demo or args.mockup):
        preview = window.security_plan_dialog([
            {"hostname": "app-linux-01", "status": "completed", "result": {
                "plan": {"status": "action_required", "actions": [{"parameter": "permitrootlogin", "current": "yes", "recommended": "prohibit-password"}], "reasons": []},
                "adapter": {"reason": "Global Include supported"}}},
            {"hostname": "db-linux-01", "status": "completed", "result": {
                "plan": {"status": "no_changes", "actions": [], "reasons": []},
                "adapter": {"reason": "Global Include supported"}}},
        ], "synthetic-plan")
        preview.show()
    if args.mockup:
        def save():
            window.graph.fit_map()
            args.mockup.parent.mkdir(parents=True, exist_ok=True)
            if not preview.grab().save(str(args.mockup)):
                raise OSError("Could not save GUI preview")
            app.quit()
        QTimer.singleShot(600, save)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Native desktop control console; operational work stays on Linux."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QDateTime
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QProgressBar, QDialog, QFormLayout,
    QSpinBox, QDialogButtonBox, QFileDialog, QMessageBox, QPlainTextEdit, QSplitter,
    QTreeWidget, QTreeWidgetItem, QComboBox, QDateTimeEdit,
)

from desktop.client import ConnectionSettings, ServerClient
from desktop.graph import ConnectionMap

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #23344c; }
QMainWindow, QDialog, QMessageBox, #workspace { background: #f3f6fb; }
#sidebar { background: #122139; }
#sidebar QLabel { color: #c0cee2; background: transparent; }
#sidebar QPushButton { color: #adbed5; text-align: left; background: transparent; border: none; padding: 13px 18px; border-radius: 8px; }
#sidebar QPushButton:checked { color: white; background: #285fc5; }
#sidebar QPushButton:hover { background: #253d60; }
#brand { color: white; font-size: 20pt; font-weight: 700; }
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
QSpinBox, QDateTimeEdit, QComboBox, QLineEdit { padding: 3px 8px; min-height: 22px; }
QTableWidget { background: white; border: none; gridline-color: #edf1f6; selection-background-color: #e6efff; selection-color: #203955; }
QHeaderView::section { background: #f7f9fc; color: #6a7c93; border: none; border-bottom: 1px solid #e1e8f0; padding: 9px; font-size: 9pt; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #eff3f7; }
QProgressBar { border: none; border-radius: 4px; background: #e9eff8; height: 8px; text-align: center; }
QProgressBar::chunk { background: #2a74df; border-radius: 4px; }
QCheckBox { spacing: 8px; }
QSplitter::handle { background: transparent; width: 12px; }
"""


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


def table(headers):
    widget = QTableWidget(0, len(headers)); widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide(); widget.setShowGrid(False)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.verticalHeader().setDefaultSectionSize(39)
    return widget


def fill_table(widget, rows):
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value)); item.setToolTip(str(value))
            widget.setItem(r, c, item)


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
        self.ca = QLineEdit(); self.ca.setPlaceholderText("Trusted server certificate / CA file")
        ca_row = QHBoxLayout(); ca_row.addWidget(self.ca)
        ca_row.addWidget(button("Browse", self.choose_ca))
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Server API token (kept in memory only)")
        form.addRow("Linux server", self.host); form.addRow("TLS port", self.port)
        form.addRow("CA certificate", ca_row); form.addRow("Access token", self.token)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def choose_ca(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose trusted certificate", "", "Certificates (*.crt *.pem);;All files (*)")
        if path:
            self.ca.setText(path)

    def settings(self):
        return ConnectionSettings(self.host.text().strip(), self.port.value(), self.ca.text().strip(), self.token.text().strip())


class InventoryDialog(QDialog):
    def __init__(self, parent, rows):
        super().__init__(parent); self.setWindowTitle("Manage server inventory"); self.resize(680, 450)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Saved encrypted on the Linux main server.", "subtitle"))
        self.grid = table(["Hostname", "IP address", "Operating system", "SSH profile"])
        self.grid.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        fill_table(self.grid, [[r["hostname"], r["ip"], r["os"], r.get("profile", "default")] for r in rows]); layout.addWidget(self.grid)
        actions = QHBoxLayout()
        actions.addWidget(button("Add server", lambda: self.grid.insertRow(self.grid.rowCount())))
        actions.addWidget(button("Remove selected", self.remove)); actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def remove(self):
        for row in sorted({item.row() for item in self.grid.selectedItems()}, reverse=True):
            self.grid.removeRow(row)

    def rows(self):
        return [{key: self.grid.item(row, col).text().strip() if self.grid.item(row, col) else ""
                 for col, key in enumerate(("hostname", "ip", "os", "profile"))} for row in range(self.grid.rowCount())]


class Console(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.setWindowTitle("SM Automation | Control Console")
        self.resize(1460, 920); self.setMinimumSize(1120, 760)
        self.client = None; self.demo = demo; self.servers = []; self.jobs = []; self.connection_results = []
        self.active_job = None; self.loaded_job = None; self.poll_busy = False; self.epoch = 0
        self.backup_history = {}
        self.backup_history_offset = 0
        self.resource_loaded_job = None
        self.workers = set()
        self.build_ui()
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(3000)
        self.resource_timer = QTimer(self); self.resource_timer.timeout.connect(self.refresh_resources); self.resource_timer.setInterval(30000)
        if demo:
            self.load_demo()

    def build_ui(self):
        base = QWidget(); self.setCentralWidget(base)
        root = QHBoxLayout(base); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar); nav.setContentsMargins(20, 28, 20, 24); nav.setSpacing(7)
        nav.addWidget(label("SM /", "brand")); nav.addWidget(label("AUTOMATION", "subtitle")); nav.addSpacing(30)
        self.nav_buttons = []
        for index, title in enumerate(["01   Overview", "02   Connection map", "03   Backups", "04   Activity", "05   Accounts", "06   Patches", "07   Schedules", "08   Resources"]):
            item = QPushButton(title); item.setCheckable(True)
            item.clicked.connect(lambda _, value=index: self.navigate(value)); nav.addWidget(item); self.nav_buttons.append(item)
        nav.addStretch(); nav.addWidget(label("LINUX MAIN SERVER"))
        self.server_badge = label("Not connected"); self.server_badge.setWordWrap(True); nav.addWidget(self.server_badge)
        nav.addWidget(button("Connect server", self.connect_server))
        nav.addWidget(button("Disconnect", self.disconnect_server))
        nav.addSpacing(20); nav.addWidget(label("Windows control console\nv0.2  /  Native desktop"))
        root.addWidget(sidebar)
        workspace = QWidget(); workspace.setObjectName("workspace"); root.addWidget(workspace, 1)
        content = QVBoxLayout(workspace); content.setContentsMargins(28, 24, 28, 18); content.setSpacing(18)
        top = QHBoxLayout(); top.addWidget(label("OPERATIONS  /  INFRASTRUCTURE", "subtitle")); top.addStretch()
        self.connection_badge = label("OFFLINE", "badge"); top.addWidget(self.connection_badge); content.addLayout(top)
        self.title = label("Infrastructure overview", "title"); content.addWidget(self.title)
        self.subtitle = label("One control console. All operational work on your Linux server.", "subtitle"); content.addWidget(self.subtitle)
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
        self.pages = QStackedWidget(); content.addWidget(self.pages, 1)
        self.build_overview(); self.build_network(); self.build_backup(); self.build_activity(); self.build_accounts(); self.build_patches(); self.build_schedules(); self.build_resources()
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.setMaximumHeight(6); content.addWidget(self.progress)
        self.status_line = label("Connect to a Linux main server to load your inventory.", "subtitle"); content.addWidget(self.status_line)
        self.navigate(0)

    def build_overview(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Your server fleet", "section"))
        actions = QHBoxLayout()
        actions.addWidget(button("Manage inventory", self.edit_inventory)); actions.addWidget(button("Import CSV", self.import_csv))
        actions.addWidget(button("Refresh", self.reload)); actions.addStretch()
        actions.addWidget(button("Resource snapshot", lambda: (self.navigate(7), self.start_job("monitoring"))))
        actions.addWidget(button("Security audit", lambda: self.start_job("security_audit")))
        actions.addWidget(button("Protect SSH config (600)", lambda: self.start_job("security_permissions")))
        actions.addWidget(button("Preview SSH policy", lambda: self.start_job("security_plan")))
        body.addLayout(actions)
        self.inventory_table = table(["Hostname", "IP address", "Operating system", "Execution"]); body.addWidget(self.inventory_table)
        body.addWidget(label("Inventory changes and collection results are stored encrypted on Linux.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def build_resources(self):
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Linux resource snapshots", "section"))
        actions = QHBoxLayout()
        actions.addWidget(button("Collect resources", lambda: self.start_job("monitoring"), True))
        self.resource_auto = QCheckBox("Refresh every 30 seconds while this console is open")
        def auto(enabled):
            if enabled:
                self.resource_timer.start(); self.refresh_resources()
            else:
                self.resource_timer.stop()
        self.resource_auto.toggled.connect(auto); actions.addWidget(self.resource_auto); actions.addStretch()
        body.addLayout(actions)
        self.resource_updated = label("No resource snapshot loaded", "subtitle"); body.addWidget(self.resource_updated)
        self.resource_table = table(["Server", "Load (1 / 5 / 15 min)", "Memory used", "Root disk used", "Uptime / status"])
        body.addWidget(self.resource_table, 1)
        note = label("Targets follow Connection map selection. Automatic refresh waits while another job is running. Load is not CPU utilization.", "subtitle")
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
            values.append([row["hostname"], " / ".join(f"{value:.2f}" for value in result.get("load_average", [])),
                           f"{percentage}% ({used:,} / {total:,} MiB)", filesystem.get("capacity", "Unavailable"), result.get("uptime", "Unavailable")])
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
        self.target_table.itemChanged.connect(self.selection_changed); left.addWidget(self.target_table)
        left.addWidget(button("Collect connections", lambda: self.start_job("connections"), True))
        note = label("Linux executes netstat over SSH.\nOnly ESTABLISHED TCP peers\nare displayed.", "subtitle"); left.addWidget(note)
        layout.addWidget(selection)
        right_frame, right = card()
        tools = QHBoxLayout(); tools.addWidget(label("Connection mind map", "section")); tools.addStretch()
        self.peer_search = QLineEdit(); self.peer_search.setPlaceholderText("Filter peer / port"); self.peer_search.setMaximumWidth(180)
        self.peer_search.textChanged.connect(self.update_map); tools.addWidget(self.peer_search)
        tools.addWidget(button("Fit", lambda: self.graph.fit_map())); right.addLayout(tools)
        self.graph = ConnectionMap(); self.graph.set_results([]); right.addWidget(self.graph, 1)
        right.addWidget(label("Blue = selected host   /   Green = connected peer   /   Scroll to zoom, drag to pan", "subtitle"))
        self.connection_table = table(["Source", "Local endpoint", "Connected peer", "Port"])
        self.connection_table.setMaximumHeight(170); right.addWidget(self.connection_table)
        layout.addWidget(right_frame, 1); self.pages.addWidget(page)

    def build_backup(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Configuration & account backups", "section"))
        text = label("Capture files and command output from every listed server.\nLinux encrypts each artifact under BACKUP / date / hostname / run ID.", "subtitle")
        text.setWordWrap(True); body.addWidget(text)
        coverage = table(["Operating system", "Configuration files", "Command snapshots"])
        fill_table(coverage, [["Linux", "sudoers + sudoers.d, SSH, PAM, cron, network", "chage per account, sudo privileges, services, storage"],
                             ["AIX", "security, filesystems, inittab, SSH, sudoers", "lsuser expiry, sudo privileges, lsvg, lssrc, packages"],
                             ["Windows (SSH)", "OpenSSH, hosts, GroupPolicy, scheduled tasks", "Local users, expiry, firewall, audit, patches"]])
        coverage.setMaximumHeight(175); body.addWidget(coverage)
        actions = QHBoxLayout(); actions.addWidget(button("Back up ALL servers", lambda: self.start_job("backup", all_hosts=True), True))
        actions.addWidget(button("Back up selected", lambda: self.start_job("backup"))); actions.addStretch(); body.addLayout(actions)
        history = QHBoxLayout()
        history.addWidget(button("Refresh backup history", lambda: self.load_backup_history(True)))
        history.addWidget(button("Load older backups", self.load_backup_history))
        history.addStretch(); body.addLayout(history)
        self.backup_table = table(["Created", "Status", "Progress", "Job ID"]); body.addWidget(self.backup_table)
        self.backup_table.cellDoubleClicked.connect(lambda row, _: self.show_job(self.backup_jobs[row]["id"]))
        body.addWidget(label("Double-click a backup to view Linux paths and per-artifact results. Partial captures are never reported as complete.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def build_activity(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        frame, body = card(); body.addWidget(label("Server-side job history", "section"))
        self.jobs_table = table(["Created", "Operation", "Status", "Progress", "Job ID"])
        self.jobs_table.cellDoubleClicked.connect(lambda row, _: self.show_job(self.jobs[row]["id"]))
        body.addWidget(self.jobs_table)
        body.addWidget(button("Cancel pending targets of selected job", self.cancel_selected_job))
        body.addWidget(label("Closing this console does not stop Linux jobs. Reconnect to see results.", "subtitle"))
        layout.addWidget(frame); self.pages.addWidget(page)

    def build_accounts(self):
        page = QWidget(); layout = QVBoxLayout(page)
        frame, body = card(); body.addWidget(label("Linux accounts", "section"))
        body.addWidget(label("Targets follow the checkboxes in Connection map. Changes require a complete encrypted backup."))
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
        body.addLayout(form)
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
        self.account_action.currentIndexChanged.connect(update_fields); update_fields()
        body.addWidget(label("New accounts have no password set. Delete retains the home directory. Lock controls password authentication."))
        body.addWidget(button("Run account operation", self.run_accounts, True))
        self.account_table = table(["Server", "Username", "UID", "GID", "Comment", "Home", "Shell"])
        body.addWidget(self.account_table, 1); layout.addWidget(frame); self.pages.addWidget(page)

    def run_accounts(self):
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
                values.append([row["hostname"], *[account[key] for key in ("username", "uid", "gid", "comment", "home", "shell")]])
        fill_table(self.account_table, values); self.navigate(4)
        self.status_line.setText(f"Account results: {len(values)} accounts; {sum(row['status'] == 'failed' for row in rows)} failed servers. Details are in Activity.")

    def build_patches(self):
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Linux patches", "section"))
        body.addWidget(label("Use Connection map to select targets. Query uses existing package metadata."))
        actions = QHBoxLayout()
        actions.addWidget(button("Query updates", self.query_patches))
        self.patch_packages = QLineEdit(); self.patch_packages.setPlaceholderText("Installed packages, separated by spaces: openssh-server net-tools")
        actions.addWidget(self.patch_packages, 1)
        actions.addWidget(button("Preview patch plan", self.plan_patches, True)); body.addLayout(actions)
        self.patch_table = table(["Server", "Package", "Installed", "Planned version"]); self.patch_table.setMinimumHeight(150); body.addWidget(self.patch_table, 2)
        self.patch_output = QPlainTextEdit(); self.patch_output.setReadOnly(True); self.patch_output.setMinimumHeight(100); body.addWidget(self.patch_output, 1)
        self.patch_plan_id = None
        self.patch_apply = button("Apply reviewed plan", self.apply_patches, True); self.patch_apply.setEnabled(False)
        body.addWidget(self.patch_apply)
        patch_note = label("Debian/Ubuntu and RHEL/DNF: reviewed plans and backed-up apply. RHEL requires prepared signed RPMs. No automatic reboot.")
        patch_note.setWordWrap(True); body.addWidget(patch_note)
        layout.addWidget(frame); self.pages.addWidget(page)

    def query_patches(self):
        self.patch_plan_id = None; self.patch_apply.setEnabled(False)
        self.start_job("patches", options={"action": "list"})

    def plan_patches(self):
        self.patch_plan_id = None; self.patch_apply.setEnabled(False)
        self.start_job("patches", options={"action": "plan", "packages": self.patch_packages.text().split()})

    def apply_patches(self):
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
                values.append([row["hostname"], package["name"], package["installed"], package["candidate"]])
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
            self.patch_apply.setEnabled(bool(rows) and all(row.get("result", {}).get("apply_supported", True) for row in rows))

    def build_schedules(self):
        self.schedules = []
        page = QWidget(); layout = QVBoxLayout(page); frame, body = card()
        body.addWidget(label("Schedules on your Linux server", "section"))
        form = QFormLayout(); self.schedule_kind = QComboBox()
        for kind in ["backup", "connections", "monitoring", "security_audit"]:
            self.schedule_kind.addItem(kind.replace("_", " ").title(), kind)
        self.schedule_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300)); self.schedule_time.setCalendarPopup(True)
        self.schedule_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.schedule_interval = QSpinBox(); self.schedule_interval.setRange(0, 525600); self.schedule_interval.setSuffix(" min (0 = once)")
        form.setVerticalSpacing(12)
        form.addRow("Operation", self.schedule_kind); form.addRow("First run (this PC local time)", self.schedule_time); form.addRow("Repeat interval", self.schedule_interval)
        body.addLayout(form)
        body.addWidget(label("Targets follow Connection map selection. Linux runs schedules while this GUI is closed."))
        body.addWidget(button("Create Linux schedule", self.create_schedule, True))
        self.schedule_table = table(["Next run", "Operation", "Targets", "Repeat (min)", "State", "Message"]); body.addWidget(self.schedule_table, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Refresh schedules", self.load_schedules))
        actions.addWidget(button("Pause selected", lambda: self.change_schedule(False)))
        actions.addWidget(button("Resume selected", lambda: self.change_schedule(True)))
        actions.addWidget(button("Delete selected", lambda: self.change_schedule(delete=True)))
        body.addLayout(actions)
        body.addWidget(label("Pause/delete stops future runs. Use Activity to cancel pending targets of a started job."))
        layout.addWidget(frame); self.pages.addWidget(page)

    def create_schedule(self):
        if not self.require_client():
            return
        client = self.client
        run_at = self.schedule_time.dateTime().toPython().astimezone().isoformat()
        hosts = self.checked_hosts(); kind = self.schedule_kind.currentData(); interval = self.schedule_interval.value() * 60
        self.work(lambda: client.call("schedule.create", kind=kind, hosts=hosts, run_at=run_at, interval_seconds=interval), lambda _: self.load_schedules())

    def load_schedules(self):
        if not self.require_client():
            return
        client = self.client
        self.work(lambda: client.call("schedule.list"), self.display_schedules)

    def display_schedules(self, schedules):
        self.schedules = schedules
        fill_table(self.schedule_table, [[s["next_run"], s["kind"], ", ".join(s["hosts"]), s["interval_seconds"] // 60, "Enabled" if s["enabled"] else "Paused / completed", s["message"]] for s in schedules])

    def change_schedule(self, enabled=None, delete=False):
        row = self.schedule_table.currentRow()
        if row < 0 or row >= len(self.schedules) or not self.require_client():
            return
        schedule_id = self.schedules[row]["id"]; client = self.client
        self.work(lambda: client.call("schedule.change", id=schedule_id, enabled=enabled, delete=delete), lambda _: self.load_schedules())

    def cancel_selected_job(self):
        row = self.jobs_table.currentRow()
        if row < 0 or row >= len(self.jobs) or not self.require_client():
            return
        job_id = self.jobs[row]["id"]; client = self.client
        self.work(lambda: client.call("job.cancel", id=job_id), lambda _: self.poll())

    def navigate(self, index):
        for metric in self.metric_cards:
            metric.setVisible(index < 4)
        self.pages.setCurrentIndex(index)
        titles = ["Infrastructure overview", "Explore your connections", "Protect your configurations", "Every operation, in view", "Manage Linux accounts", "Plan your Linux patches", "Keep operations on schedule", "Watch your Linux resources"]
        self.title.setText(titles[index])
        descriptions = ["One control console. All operational work on your Linux server.",
                        "Selected servers and their established TCP peers. All collection runs on Linux.",
                        "OS configuration files and account information, encrypted and retained on Linux.",
                        "Follow server-side jobs and inspect their results, even after reconnecting.",
                        "Account changes run on Linux after an encrypted backup.",
                        "Preview exact versions, then apply the reviewed plan from your Linux main server.",
                        "Encrypted Linux schedules continue independently of your Windows console.",
                        "Linux collects load, memory and root disk observations over SSH."]
        self.subtitle.setText(descriptions[index])
        for i, item in enumerate(self.nav_buttons):
            item.setChecked(i == index)
        if index == 1:
            QTimer.singleShot(50, self.graph.fit_map)
        if index == 6 and self.client:
            self.load_schedules()

    def work(self, fn, done, quiet=False):
        worker = Worker(fn); self.workers.add(worker)
        epoch = self.epoch
        def success(result):
            self.workers.discard(worker)
            if epoch == self.epoch:
                done(result)
        def failure(message):
            self.workers.discard(worker); self.poll_busy = False
            if epoch != self.epoch:
                return
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
        if not settings.host or not settings.ca_file or not settings.token:
            QMessageBox.warning(self, "Connection details", "Server, CA certificate and access token are required."); return
        client = ServerClient(settings)
        self.connect_to(client)

    def attach_client(self, client, status):
        settings = client.settings
        self.epoch += 1; self.client = client; self.loaded_job = None; self.active_job = None
        self.backup_history = {}
        self.backup_history_offset = 0
        self.resource_loaded_job = None
        self.server_badge.setText(f"{settings.host}\nTLS : {settings.port}")
        self.connection_badge.setText("CONNECTED  /  TLS")
        self.subtitle.setText(f"Execution: Linux main server   |   Data: {status['data_directory']}")
        self.status_line.setText("Connected. All operational work executes on Linux."); self.reload()

    def connect_to(self, client):
        self.status_line.setText("Connecting to Linux main server...")
        self.work(lambda: client.call("status"), lambda status: self.attach_client(client, status))

    def disconnect_server(self):
        if self.demo:
            return
        self.epoch += 1; self.client = None; self.active_job = None; self.poll_busy = False
        self.backup_history = {}
        self.backup_history_offset = 0
        self.resource_auto.setChecked(False); self.resource_loaded_job = None
        self.resource_table.setRowCount(0); self.resource_updated.setText("No resource snapshot loaded")
        self.connection_results = []; self.jobs = []; self.set_inventory([]); self.update_map(); self.set_jobs([])
        self.metric_values[2].setText("—"); self.progress.setValue(0)
        self.server_badge.setText("Not connected"); self.connection_badge.setText("OFFLINE")
        self.subtitle.setText("One control console. All operational work on your Linux server.")
        self.status_line.setText("Disconnected. Jobs already submitted continue on Linux.")

    def require_client(self):
        if not self.client:
            QMessageBox.information(self, "Linux connection required", "Connect to the Linux main server first. Demo mode never runs operations.")
            return False
        return True

    def reload(self):
        if not self.require_client():
            return
        client = self.client
        self.work(lambda: client.call("inventory.list"), self.set_inventory)
        self.poll()

    def set_inventory(self, servers):
        self.servers = servers; self.metric_values[0].setText(str(len(servers)))
        fill_table(self.inventory_table, [[r["hostname"], r["ip"], r["os"], "Linux main server / SSH"] for r in servers])
        self.target_table.blockSignals(True); self.target_table.setRowCount(len(servers))
        for row, server in enumerate(servers):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked); self.target_table.setItem(row, 0, check)
            item = QTableWidgetItem(server["hostname"] + "\n" + server["ip"])
            item.setToolTip(server["os"]); self.target_table.setItem(row, 1, item); self.target_table.setRowHeight(row, 60)
        self.target_table.blockSignals(False)
        self.select_all.blockSignals(True); self.select_all.setChecked(True); self.select_all.blockSignals(False)
        self.selection_changed(); self.filter_servers(self.server_search.text())

    def checked_hosts(self):
        return [server["hostname"] for row, server in enumerate(self.servers)
                if self.target_table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def selection_changed(self, *_):
        hosts = self.checked_hosts(); self.metric_values[1].setText(str(len(hosts)))
        self.select_all.blockSignals(True); self.select_all.setChecked(bool(self.servers) and len(hosts) == len(self.servers)); self.select_all.blockSignals(False)

    def check_all(self, checked):
        self.target_table.blockSignals(True)
        for row in range(self.target_table.rowCount()):
            self.target_table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.target_table.blockSignals(False); self.selection_changed()

    def filter_servers(self, query):
        for row, server in enumerate(self.servers):
            self.target_table.setRowHidden(row, query.casefold() not in (server["hostname"] + server["ip"]).casefold())

    def edit_inventory(self):
        if not self.require_client():
            return
        dialog = InventoryDialog(self, self.servers)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rows = dialog.rows(); client = self.client
            self.work(lambda: client.call("inventory.save", servers=rows), lambda _: self.reload())

    def import_csv(self):
        if not self.require_client():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import hostname,ip,os CSV (replaces inventory)", "", "Inventory (*.csv *.txt)")
        if path:
            try:
                content = Path(path).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                QMessageBox.warning(self, "Import failed", str(exc)); return
            client = self.client
            self.work(lambda: client.call("inventory.import", csv=content), lambda _: self.reload())

    def start_job(self, kind, all_hosts=False, options=None):
        if not self.require_client():
            return
        hosts = [row["hostname"] for row in self.servers] if all_hosts else self.checked_hosts()
        if not hosts:
            QMessageBox.information(self, "Select targets", "Select at least one server in Connection map."); return
        client = self.client
        def started(job):
            self.active_job = job["id"]; self.loaded_job = None
            self.status_line.setText(f"{kind}: submitted to Linux for {len(hosts)} servers."); self.poll()
        self.work(lambda: client.call("job.start", kind=kind, hosts=hosts, options=options or {}), started)

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
        self.work(lambda: client.call("job.list", kind="backup", offset=offset), loaded)

    def display_backup_history(self, jobs):
        self.backup_history.update({job["id"]: job for job in jobs})
        self.backup_jobs = sorted(self.backup_history.values(), key=lambda job: (job["created_at"], job["id"]), reverse=True)
        fill_table(self.backup_table, [[j["created_at"], j["status"], f"{j['done']}/{j['total']}", j["id"][:12]] for j in self.backup_jobs])

    def set_jobs(self, jobs):
        self.poll_busy = False; self.jobs = jobs
        fill_table(self.jobs_table, [[j["created_at"][11:19], j["kind"], j["status"], f"{j['done']}/{j['total']}", j["id"][:12]] for j in jobs])
        self.display_backup_history([j for j in jobs if j["kind"] == "backup"])
        resource = next((job for job in jobs if job["kind"] == "monitoring" and job["status"] not in {"queued", "running"}), None)
        if resource and resource["id"] != self.resource_loaded_job and self.client:
            self.resource_loaded_job = resource["id"]; client = self.client
            self.work(lambda: client.results(resource["id"]), lambda rows: self.display_resources(rows, resource.get("finished_at", resource["created_at"])), quiet=True)
        active = next((j for j in jobs if j["id"] == self.active_job), None)
        if active:
            self.progress.setValue(int(100 * active["done"] / max(1, active["total"])))
            self.status_line.setText(f"{active['kind']} / {active['status']} / {active.get('message', '')}")
            if active["status"] not in {"queued", "running"} and self.loaded_job != active["id"]:
                self.loaded_job = active["id"]
                if active["kind"] == "connections":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), self.display_connections)
                elif active["kind"] == "accounts":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), self.display_accounts)
                elif active["kind"] == "patches":
                    client = self.client
                    self.work(lambda: client.results(active["id"]), lambda rows: self.display_patches(rows, active))

    def display_connections(self, rows):
        self.connection_results = rows
        total = sum(len(row.get("result", {}).get("connections", [])) for row in rows)
        self.metric_values[2].setText(str(total)); self.update_map(); self.navigate(1)
        failures = sum(row["status"] == "failed" for row in rows)
        truncated = any(row.get("result", {}).get("truncated") for row in rows)
        self.status_line.setText(f"Snapshot loaded: {total} established connections, {failures} failed servers." +
                                 (" Large results limited to 5,000 connections per host." if truncated else ""))

    def update_map(self, *_):
        query = self.peer_search.text()
        self.graph.set_results(self.connection_results, query)
        rows = []
        for row in self.connection_results:
            for connection in row.get("result", {}).get("connections", []):
                local, remote = connection["local"], connection["remote"]
                values = [row["hostname"], f"{local['address']}:{local['port']}", remote["address"], remote["port"]]
                if not query or query.casefold() in " ".join(values).casefold():
                    rows.append(values)
        fill_table(self.connection_table, rows)

    def show_job(self, job_id):
        if not self.require_client():
            return
        client = self.client
        def show(rows):
            job = next((item for item in self.jobs if item["id"] == job_id), self.backup_history.get(job_id, {}))
            if job.get("kind") == "connections":
                self.display_connections(rows); return
            if job.get("kind") == "backup":
                self.show_backup_results(rows); return
            if job.get("kind") == "monitoring":
                self.display_resources(rows, job.get("finished_at", job.get("created_at", ""))); self.navigate(7); return
            if job.get("kind") == "security_audit":
                from desktop.security import audit_rows
                dialog = QDialog(self); dialog.setWindowTitle("Linux security observations"); dialog.resize(980, 560)
                layout = QVBoxLayout(dialog)
                layout.addWidget(label("Review flags are guidance. No security policy has been changed."))
                findings = table(["Server", "Setting", "Observed value", "Assessment"])
                fill_table(findings, audit_rows(rows)); layout.addWidget(findings)
                layout.addWidget(button("Close", dialog.accept)); dialog.exec(); return
            if job.get("kind") == "security_plan":
                self.security_plan_dialog(rows, job_id, job.get("status") == "completed").exec(); return
            dialog = QDialog(self); dialog.setWindowTitle("Linux job results"); dialog.resize(880, 620)
            layout = QVBoxLayout(dialog); text = QPlainTextEdit(); text.setReadOnly(True)
            text.setPlainText(json.dumps(rows, ensure_ascii=False, indent=2)); layout.addWidget(text)
            layout.addWidget(button("Close", dialog.accept)); dialog.exec()
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
        layout.addWidget(button("Close", dialog.accept))
        return dialog

    def show_backup_results(self, rows):
        self.backup_results_dialog(rows).exec()

    def backup_results_dialog(self, rows):
        dialog = QDialog(self); dialog.setWindowTitle("Backup artifacts on Linux"); dialog.resize(1060, 720)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Browse encrypted backups", "section"))
        layout.addWidget(label("Double-click an artifact to preview text or list archive files. Decryption runs on Linux.", "subtitle"))
        tree = QTreeWidget(); tree.setHeaderLabels(["Server / artifact", "Status", "Size", "Linux storage path"])
        tree.setStyleSheet("QTreeWidget { background: white; color: #20354d; alternate-background-color: #f4f7fb; } QTreeWidget::item:selected { background: #dbeafe; color: #172d48; }")
        tree.setAlternatingRowColors(True)
        tree.setColumnWidth(0, 260); tree.setColumnWidth(1, 100); tree.setColumnWidth(2, 90)
        for row in rows:
            result = row.get("result", {})
            parent = QTreeWidgetItem([row["hostname"], row["status"], "", result.get("directory", row.get("error", ""))])
            tree.addTopLevelItem(parent)
            for artifact in result.get("artifacts", []):
                path = artifact.get("path", "")
                item = QTreeWidgetItem([artifact["name"], artifact["status"],
                                        f"{artifact.get('size', 0):,} B", path or artifact.get("error", "")])
                item.setData(0, Qt.ItemDataRole.UserRole, path); parent.addChild(item)
                details = []
                if "exit_code" in artifact:
                    details.append(f"Command exit code: {artifact['exit_code']}")
                if artifact.get("error"):
                    details.append("Collection error: " + artifact["error"])
                details.extend(artifact.get("warnings", []))
                for detail in details:
                    child = QTreeWidgetItem([detail, "", "", ""])
                    child.setToolTip(0, detail)
                    item.addChild(child)
                if path:
                    metadata = path.rsplit("/", 1)[0] + "/" + artifact["name"] + ".metadata.json.enc"
                    child = QTreeWidgetItem(["Command details and diagnostic output", "", "", metadata])
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
        layout.addWidget(button("Close", dialog.accept))
        return dialog

    def load_demo(self):
        from desktop.demo import SERVERS, connection_rows
        self.set_inventory(SERVERS)
        self.target_table.item(3, 0).setCheckState(Qt.CheckState.Unchecked)
        self.server_badge.setText("sm-main.example.internal\nTLS : 7443 / Preview")
        self.connection_badge.setText("DEMO  /  SYNTHETIC DATA")
        self.subtitle.setText("Selected servers and their established TCP peers. All collection runs on Linux.")
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
    parser.add_argument("--page", choices=["overview", "connections", "backups", "activity", "accounts", "patches", "schedules", "resources", "security", "backup-details"], default="connections")
    parser.add_argument("--mockup", type=Path, help="Render synthetic demo to PNG without connecting to any server")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    if sys.platform == "win32":
        for filename in ("segoeui.ttf", "segoeuib.ttf"):
            font_file = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font_file.exists():
                QFontDatabase.addApplicationFont(str(font_file))
    app.setFont(QFont("Segoe UI", 10)); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    window = Console(demo=args.demo or bool(args.mockup)); window.show()
    if args.demo or args.mockup:
        window.navigate(["overview", "connections", "backups", "activity", "accounts", "patches", "schedules", "resources"].index(args.page) if args.page not in {"security", "backup-details"} else 3)
    preview = window
    if args.page == "backup-details" and (args.demo or args.mockup):
        prefix = "2026-10-09/app-rhel-01/synthetic-run"
        preview = window.backup_results_dialog([{
            "hostname": "app-rhel-01", "status": "partial", "result": {"directory": "BACKUP/" + prefix,
            "artifacts": [
                {"name": "configuration_files", "status": "completed", "size": 204800,
                 "path": prefix + "/configuration_files.tar.enc", "exit_code": 0,
                 "warnings": ["Missing optional path: /etc/netplan"]},
                {"name": "network", "status": "partial", "size": 4096,
                 "path": prefix + "/network.txt.enc", "exit_code": 1},
                {"name": "account_expiry_chage", "status": "failed",
                 "error": "Synthetic example: remote command timed out"},
            ]}}])
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

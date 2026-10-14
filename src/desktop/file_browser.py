"""Two-pane Windows/Linux file browser with bounded-memory transfers."""
import base64
import json
import os
import posixpath
import uuid
from pathlib import Path
from PySide6.QtCore import Qt, QMimeData, QThread, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QSplitter, QLabel, QFileDialog)


from desktop.tables import SortTreeItem
from desktop.theme import LIGHT_CONTROLS, light_palette


class Task(QThread):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, function, parent):
        super().__init__(parent); self.function = function

    def run(self):
        try: self.result.emit(self.function(self.progress.emit))
        except Exception as exc: self.error.emit(str(exc))


class FileList(QTreeWidget):
    dropped = Signal(object)
    def __init__(self, side):
        super().__init__(); self.side = side
        self.setHeaderLabels(['Name', 'Type', 'Bytes'])
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True); self.setAcceptDrops(True)
        self.setColumnWidth(0, 280)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True); self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def startDrag(self, actions):
        files = [i.data(0, Qt.ItemDataRole.UserRole) for i in self.selectedItems()]
        files = [f for f in files if f['regular'] or f.get('directory')]
        if not files: return
        mime = QMimeData(); mime.setData('application/x-sm-files', json.dumps({'side': self.side, 'files': files}).encode())
        drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-sm-files') or (self.side == 'remote' and event.mimeData().hasUrls()): event.acceptProposedAction()

    def dragMoveEvent(self, event): self.dragEnterEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-sm-files'):
            payload = json.loads(bytes(mime.data('application/x-sm-files')))
            if payload['side'] == self.side: return
        elif self.side == 'remote' and mime.hasUrls():
            payload = {'side': 'local', 'files': [{'path': u.toLocalFile(), 'regular': True} for u in mime.urls() if u.isLocalFile() and (Path(u.toLocalFile()).is_file() or Path(u.toLocalFile()).is_dir())]}
        else: return
        self.dropped.emit(payload); event.acceptProposedAction()


class FileBrowser(QDialog):
    def __init__(self, client, parent=None):
        super().__init__(parent); self.setPalette(light_palette()); self.client = client; self.task = None
        self.setStyleSheet("""
            QDialog, QWidget { background: #f3f6fb; color: #20354d; }
            QTreeWidget { background: #ffffff; color: #20354d;
                alternate-background-color: #f0f5fb; border: 1px solid #cbd5e1; }
            QTreeWidget::item { min-height: 28px; padding: 3px; }
            QTreeWidget::item:hover { background: #e6effc; color: #172d48; }
            QTreeWidget::item:selected { background: #cfe2ff; color: #102a4c; }
            QHeaderView::section { background: #e4ecf7; color: #172d48;
                padding: 8px; border: 1px solid #cbd5e1; font-weight: bold; }
            QLineEdit { background: #ffffff; color: #20354d;
                selection-background-color: #cfe2ff; selection-color: #102a4c; }
            QPushButton { background: #ffffff; color: #20354d; border: 1px solid #cbd5e1; }
            QPushButton:hover { background: #e6effc; }
            QSplitter::handle { background: #d6dfec; }
        """ + LIGHT_CONTROLS)
        self.setWindowTitle('GUI (Windows) ↔ SERVER (Linux) — File browser'); self.resize(1100, 680)
        layout = QVBoxLayout(self); splitter = QSplitter(); layout.addWidget(splitter)
        from desktop.transfers import Transfers
        import hashlib
        settings=client.settings
        identity=hashlib.sha256(str((settings.host, settings.port, settings.username)).encode()).hexdigest()
        state=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'SM_Automation'/'transfers'/(identity+'.json')
        self.transfers=Transfers(client,state)
        self.pause_requested=False
        self.paths = {}; self.lists = {}
        for side, title, path in [('local', 'GUI · Windows', str(Path.home())), ('remote', 'SERVER · Linux', '/')]:
            from PySide6.QtWidgets import QWidget
            pane = QWidget(); box = QVBoxLayout(pane); box.addWidget(QLabel(title))
            bar = QHBoxLayout(); edit = QLineEdit(path); self.paths[side] = edit; bar.addWidget(edit)
            go = QPushButton('Open / Refresh'); go.clicked.connect(lambda checked=False, s=side: self.refresh(s)); bar.addWidget(go)
            up = QPushButton('↑'); up.clicked.connect(lambda checked=False, s=side: self.up(s)); bar.addWidget(up)
            if side == 'local':
                choose = QPushButton('Folder…'); choose.clicked.connect(self.choose); bar.addWidget(choose)
            box.addLayout(bar); tree = FileList(side); self.lists[side] = tree; box.addWidget(tree)
            edit.returnPressed.connect(lambda s=side: self.refresh(s))
            tree.itemDoubleClicked.connect(lambda item, col, s=side: self.enter(s, item))
            tree.dropped.connect(self.transfer); splitter.addWidget(pane)
        buttons = QHBoxLayout(); self.upload_button = None
        for side, text in [('local', 'Upload →'), ('remote', '← Download')]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, s=side: self.selected(s)); buttons.addWidget(button)
            if side == "local": self.upload_button = button
        for text,callback in [('Pause',self.pause),('Resume',self.resume),('Discard paused transfer',self.discard)]:
            action=QPushButton(text);action.clicked.connect(callback);buttons.addWidget(action)
        cancel = QPushButton('Cancel transfer'); cancel.clicked.connect(self.cancel); buttons.addWidget(cancel)
        layout.addLayout(buttons); self.status = QLabel('Drag files between panes. Files and folders. No file-size limit. Pause / Resume survives GUI restart.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.refresh('local'); self.refresh('remote')

    def run_task(self, function, callback):
        if self.task and self.task.isRunning(): self.status.setText('Wait for the current operation to finish.'); return
        self.task = Task(function, self); self.task.result.connect(callback); self.task.error.connect(self.status.setText); self.task.progress.connect(self.status.setText); self.task.start()

    def populate(self, side, entries):
        tree = self.lists[side]; tree.clear()
        for entry in entries:
            item = SortTreeItem([entry['name'], 'Folder' if entry['directory'] else 'File' if entry['regular'] else 'Link / special', str(entry['size']) if not entry['directory'] else ''])
            item.setData(0, Qt.ItemDataRole.UserRole, entry); tree.addTopLevelItem(item)

    def refresh(self, side):
        path = self.paths[side].text().strip()
        if side == 'remote':
            def ready(result):
                self.paths[side].setText(result['path'])
                self.upload_button.setEnabled(result.get('role','admin') != 'viewer')
                for e in result['entries']: e['path'] = posixpath.join(result['path'], e['name'])
                self.populate(side, result['entries'])
            def listing(progress):
                role=self.client.call('session.info')['role']
                destination='/srv/sm-automation/shared' if role!='admin' and path=='/' else path
                result=self.client.call('file.list',path=destination);result['role']=role
                return result
            self.run_task(listing, ready)
        else:
            try:
                entries = []
                for p in Path(path).iterdir():
                    info = p.lstat(); entries.append({'name': p.name, 'path': str(p), 'directory': p.is_dir() and not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(), 'regular': p.is_file() and not p.is_symlink(), 'size': info.st_size})
                self.populate(side, sorted(entries, key=lambda e: (not e['directory'], e['name'].lower())))
            except OSError as exc: self.status.setText(str(exc))

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, 'Windows folder', self.paths['local'].text())
        if path: self.paths['local'].setText(path); self.refresh('local')

    def up(self, side):
        path = self.paths[side].text(); self.paths[side].setText(str(Path(path).parent) if side == 'local' else posixpath.dirname(path.rstrip('/')) or '/'); self.refresh(side)

    def enter(self, side, item):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry['directory']: self.paths[side].setText(entry['path']); self.refresh(side)

    def selected(self, side):
        self.transfer({'side': side, 'files': [i.data(0, Qt.ItemDataRole.UserRole) for i in self.lists[side].selectedItems() if i.data(0, Qt.ItemDataRole.UserRole)['regular'] or i.data(0, Qt.ItemDataRole.UserRole)['directory']]})

    def cancel(self):
        if self.task and self.task.isRunning():
            self.task.requestInterruption(); self.status.setText('Cancelling after the current chunk…')

    def pause(self):
        if self.task and self.task.isRunning():
            self.pause_requested=True;self.task.requestInterruption()
            self.status.setText('Pausing after the current chunk…')

    def resume(self):
        self.start_transfer(None,True)

    def discard(self):
        self.run_task(lambda progress:self.transfers.discard() or 'Paused transfer discarded.',self.status.setText)

    def transfer(self,payload):
        self.start_transfer(payload,False)

    def start_transfer(self,payload,resume):
        if self.task and self.task.isRunning():
            self.status.setText('Wait for the current operation to finish.');return
        self.pause_requested=False
        local_dir=self.paths['local'].text();remote_dir=self.paths['remote'].text()
        def stop():
            return ('pause' if self.pause_requested else 'cancel') if self.task.isInterruptionRequested() else ''
        def copy(progress):
            return self.transfers.run(payload,local_dir,remote_dir,progress,stop,resume)
        def done(message):
            self.status.setText(message);self.refresh('local')
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50,lambda:self.refresh('remote'))
        self.run_task(copy,done)

    def reject(self):
        if self.task and self.task.isRunning(): self.status.setText('Transfer is running. Close after it finishes.'); return
        super().reject()

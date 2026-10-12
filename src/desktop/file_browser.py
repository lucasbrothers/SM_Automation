"""Two-pane Windows/Linux file browser with bounded-memory transfers."""
import base64
import json
import os
import posixpath
from pathlib import Path
from PySide6.QtCore import Qt, QMimeData, QThread, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QSplitter, QLabel, QFileDialog)


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

    def startDrag(self, actions):
        files = [i.data(0, Qt.ItemDataRole.UserRole) for i in self.selectedItems()]
        files = [f for f in files if f['regular']]
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
            payload = {'side': 'local', 'files': [{'path': u.toLocalFile(), 'regular': True} for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).is_file()]}
        else: return
        self.dropped.emit(payload); event.acceptProposedAction()


class FileBrowser(QDialog):
    def __init__(self, client, parent=None):
        super().__init__(parent); self.client = client; self.task = None
        self.setWindowTitle('GUI (Windows) ↔ SERVER (Linux) — File browser'); self.resize(1100, 680)
        layout = QVBoxLayout(self); splitter = QSplitter(); layout.addWidget(splitter)
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
        buttons = QHBoxLayout()
        for side, text in [('local', 'Upload →'), ('remote', '← Download')]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, s=side: self.selected(s)); buttons.addWidget(button)
        layout.addLayout(buttons); self.status = QLabel('Drag files between panes. No file-size limit. Existing files are preserved.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.refresh('local'); self.refresh('remote')

    def run_task(self, function, callback):
        if self.task and self.task.isRunning(): self.status.setText('Wait for the current operation to finish.'); return
        self.task = Task(function, self); self.task.result.connect(callback); self.task.error.connect(self.status.setText); self.task.progress.connect(self.status.setText); self.task.start()

    def populate(self, side, entries):
        tree = self.lists[side]; tree.clear()
        for entry in entries:
            item = QTreeWidgetItem([entry['name'], 'Folder' if entry['directory'] else 'File' if entry['regular'] else 'Link / special', str(entry['size']) if not entry['directory'] else ''])
            item.setData(0, Qt.ItemDataRole.UserRole, entry); tree.addTopLevelItem(item)

    def refresh(self, side):
        path = self.paths[side].text().strip()
        if side == 'remote':
            def ready(result):
                self.paths[side].setText(result['path'])
                for e in result['entries']: e['path'] = posixpath.join(result['path'], e['name'])
                self.populate(side, result['entries'])
            self.run_task(lambda progress: self.client.call('file.list', path=path), ready)
        else:
            try:
                entries = []
                for p in Path(path).iterdir():
                    info = p.lstat(); entries.append({'name': p.name, 'path': str(p), 'directory': p.is_dir(), 'regular': p.is_file() and not p.is_symlink(), 'size': info.st_size})
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
        self.transfer({'side': side, 'files': [i.data(0, Qt.ItemDataRole.UserRole) for i in self.lists[side].selectedItems() if i.data(0, Qt.ItemDataRole.UserRole)['regular']]})

    def transfer(self, payload):
        local_dir = self.paths['local'].text(); remote_dir = self.paths['remote'].text()
        def copy(progress):
            messages = []
            for entry in payload['files']:
                source = entry['path']; name = Path(source).name if payload['side'] == 'local' else posixpath.basename(source)
                try:
                    offset = 0
                    if payload['side'] == 'local':
                        total = os.path.getsize(source)
                        with open(source, 'rb') as stream:
                            while True:
                                data = stream.read(1024*1024)
                                if not data and offset < total: raise RuntimeError('Source changed during upload')
                                self.client.call('file.upload', path=posixpath.join(remote_dir, name), offset=offset, content=base64.b64encode(data).decode(), final=offset+len(data)>=total)
                                offset += len(data); progress(f'Upload {name}: {offset:,} / {total:,} bytes')
                                if offset >= total: break
                    else:
                        destination = Path(local_dir)/name
                        with destination.open('xb') as stream:
                            while True:
                                result = self.client.call('file.download', path=source, offset=offset)
                                data = base64.b64decode(result['content'], validate=True); stream.write(data); offset += len(data)
                                progress(f'Download {name}: {offset:,} / {result["size"]:,} bytes')
                                if offset >= result['size']: break
                                if not data: raise RuntimeError('Source changed during download')
                    messages.append(name + ': Success')
                except Exception as exc: messages.append(name + ': Failed — ' + str(exc) + ' (partial file may remain)')
            return '\n'.join(messages) or 'Select regular files to transfer.'
        def done(message):
            self.status.setText(message); self.refresh('local')
            # Worker has finished before the queued refresh starts.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.refresh('remote'))
        self.run_task(copy, done)

    def reject(self):
        if self.task and self.task.isRunning(): self.status.setText('Transfer is running. Close after it finishes.'); return
        super().reject()

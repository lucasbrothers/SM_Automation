"""Windows GUI / local WSL file acceptance with large, failed and cancelled transfers."""
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from desktop.client import ConnectionSettings,ServerClient
from desktop.file_browser import FileBrowser
from PySide6.QtWidgets import QApplication

def main():
    if sys.platform!='win32':raise SystemExit('Run on Windows against approved local WSL')
    command=lambda args:subprocess.check_output(['wsl','-d','Ubuntu','-u','root','--',*args],creationflags=subprocess.CREATE_NO_WINDOW)
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='sm-gui-check-') as directory:
        root=Path(directory);ca=root/'ca.crt';ca.write_bytes(command(['cat','/root/.config/sm-automation/ca.crt']))
        client=ServerClient(ConnectionSettings(command(['hostname','-I']).decode().split()[0],7443,str(ca),command(['cat','/root/.config/sm-automation/api.token']).decode().strip()))
        name='sm-gui-check-'+uuid.uuid4().hex+'.bin';remote='/tmp/'+name;source=root/name
        with source.open('wb') as stream:
            for _ in range(64):stream.write(bytes(range(256))*4096)
        def digest(path):
            with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').digest()
        browser=FileBrowser(client)
        def wait():
            deadline=time.monotonic()+90
            while browser.task.isRunning():
                app.processEvents();time.sleep(.01)
                if time.monotonic()>deadline:raise RuntimeError('Transfer timed out')
            for _ in range(15):app.processEvents();time.sleep(.01)
        wait();browser.paths['remote'].setText('/tmp');browser.paths['local'].setText(str(root))
        item={'path':str(source),'regular':True}
        try:
            browser.transfer({'side':'local','files':[item]});wait()
            assert ': Success' in browser.status.text(),browser.status.text()
            downloaded=root/'downloaded';downloaded.mkdir();browser.paths['local'].setText(str(downloaded))
            browser.transfer({'side':'remote','files':[{'path':remote,'regular':True}]});wait()
            assert digest(source)==digest(downloaded/name)
            print('PASS: 64 MiB GUI SERVER binary roundtrip and host /tmp visibility')
            with source.open('r+b') as stream:stream.write(b'changed')
            browser.transfer({'side':'local','files':[item]});wait()
            assert 'incomplete' in browser.status.text()
            browser.discard();wait()
            assert client.call('file.download',path=remote)['size']==source.stat().st_size
            assert not any(e['name'].startswith('.sm-upload-') for e in client.call('file.list',path='/tmp')['entries'])
            print('PASS: existing file preserved, failed upload staging removed')
            cancel_source=root/('sm-cancel-'+uuid.uuid4().hex);source.rename(cancel_source)
            browser.transfer({'side':'local','files':[{'path':str(cancel_source),'regular':True}]})
            browser.task.progress.connect(lambda text:browser.cancel())
            wait()
            assert 'cancelled' in browser.status.text().lower(),browser.status.text()
            names={e['name'] for e in client.call('file.list',path='/tmp')['entries']}
            assert cancel_source.name not in names and not any(n.startswith('.sm-upload-') for n in names)
            print('PASS: cancel leaves no final or pending upload')
        finally:
            if browser.task.isRunning():browser.task.wait(90000)
            browser.reject();command(['rm','-f','--',remote])

if __name__=='__main__':main()

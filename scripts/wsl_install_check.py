"""Install the SERVER ZIP in an isolated approved WSL directory and exercise TLS."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

def main():
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Only local WSL is supported')
    archive=Path(__file__).resolve().parents[1]/'release/server-install.zip'
    with tempfile.TemporaryDirectory(prefix='sm-fresh-install-') as folder:
        root=Path(folder);project=root/'application';project.mkdir();secure=root/'secrets'
        with zipfile.ZipFile(archive) as source:source.extractall(project)
        subprocess.run(['bash','deploy/install-server.sh'],cwd=project,check=True,stdout=subprocess.DEVNULL)
        python=project/'.venv/bin/python'
        subprocess.run([str(python),'scripts/provision_server.py','--secrets-dir',str(secure),'--server-name','localhost','--server-ip','127.0.0.1'],cwd=project,check=True,stdout=subprocess.DEVNULL)
        config=project/'config/app.local.json';data=json.loads(config.read_text())
        data['storage']={'data_directory':str(root/'DATA'),'backup_directory':str(root/'BACKUP'),'key_file':str(secure/'master.key')}
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        data['server'].update(host='127.0.0.1',port=port,tls_cert=str(secure/'server.crt'),tls_key=str(secure/'server.key'),token_file=str(secure/'api.token'))
        config.write_text(json.dumps(data))
        sys.path.insert(0,str(project/'src'))
        # Server dependencies are installed in the new venv; verify through a subprocess.
        env=os.environ.copy();env['PYTHONPATH']=str(project/'src')
        password=secrets.token_urlsafe(32)
        subprocess.run([str(python),'-c','from common.config import load_config; from storage.encrypted import EncryptedStore; from server.auth import save_account; import sys; c=load_config(sys.argv[1]); save_account(EncryptedStore(c.data_directory,c.key_file), "acceptance", sys.stdin.read())',str(config)],cwd=project,env=env,input=password.encode(),check=True)
        process=subprocess.Popen([str(python),'scripts/run_server.py','--config',str(config)],cwd=project,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+20
            while True:
                if process.poll() is not None:raise RuntimeError('Fresh server exited')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                except OSError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.1)
            code='import ssl,socket,sys; from shared.protocol import send,receive; c=ssl.create_default_context(cafile=sys.argv[2]); s=c.wrap_socket(socket.create_connection(("127.0.0.1",int(sys.argv[1]))),server_hostname="127.0.0.1"); send(s,{"method":"status","params":{},"username":"acceptance","password":sys.stdin.read()}); r=receive(s); assert r["ok"], r.get("error"); print("PASS: isolated SERVER ZIP install, provisioning, app login and verified TLS startup")'
            subprocess.run([str(python),'-c',code,str(port),str(secure/'ca.crt')],env=env,input=password.encode(),check=True)
        finally:process.terminate();process.wait(timeout=20)

if __name__=='__main__':main()

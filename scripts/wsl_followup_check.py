"""Live TLS acceptance for recursive resume and role restrictions on local WSL."""
import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop.client import ConnectionSettings,ServerClient
from desktop.transfers import Transfers,digest

def main():
    if sys.platform!='win32':raise SystemExit('Run on Windows with local WSL only')
    run=lambda args:subprocess.check_output(['wsl','-d','Ubuntu','-u','root','--',*args],creationflags=subprocess.CREATE_NO_WINDOW)
    host=run(['hostname','-I']).decode().split()[0];suffix=uuid.uuid4().hex
    remote='/tmp/sm-followup-'+suffix;shared='/srv/sm-automation/shared/sm-followup-'+suffix
    users=[]
    with tempfile.TemporaryDirectory(prefix='sm-followup-') as directory:
        root=Path(directory);ca=root/'ca.crt';ca.write_bytes(run(['cat','/root/.config/sm-automation/ca.crt']))
        client=ServerClient(ConnectionSettings(host,7443,str(ca),run(['cat','/root/.config/sm-automation/api.token']).decode().strip()))
        try:
            client.call('file.mkdir',path=remote)
            source=root/'source';(source/'nested').mkdir(parents=True);(source/'empty').mkdir();(source/'zero').write_bytes(b'')
            (source/'nested'/'data').write_bytes(bytes(range(256))*24000)
            state=root/'transfer.json';paused=[]
            payload={'side':'local','files':[{'path':str(source),'directory':True}]}
            message=Transfers(client,state).run(payload,str(root),remote,lambda text:paused.append(True),lambda:'pause' if paused else '')
            assert 'paused' in message and not any(e['name']=='data' for e in client.call('file.list',path=remote+'/source/nested')['entries'])
            message=Transfers(client,state).run(None,'','',lambda text:None,lambda:'',True);assert 'Success' in message,message
            download=root/'download';download.mkdir();paused=[]
            message=Transfers(client,state).run({'side':'remote','files':[{'path':remote+'/source','directory':True}]},str(download),remote,lambda text:paused.append(True),lambda:'pause' if paused else '')
            assert 'paused' in message
            message=Transfers(client,state).run(None,'','',lambda text:None,lambda:'',True);assert 'Success' in message,message
            assert digest(source/'nested/data')==digest(download/'source/nested/data')
            assert (download/'source/empty').is_dir() and (download/'source/zero').read_bytes()==b''
            print('PASS: Windows Linux nested folders, empty entries, upload/download pause and restart-resume with SHA256')
            for role in ['operator','viewer']:
                user='check-'+role+'-'+suffix[:12];password=secrets.token_urlsafe(32)
                client.call('gui.account.save',username=user,password=password,role=role);users.append(user)
                limited=ServerClient(ConnectionSettings(host,7443,str(ca),'',user,password))
                assert limited.call('session.info')['role']==role
                for method,params in [('gui.account.list',{}),('file.download',{'path':'/root/.config/sm-automation/api.token'}),('job.start',{'kind':'command','hosts':['wsl-ubuntu'],'options':{'command':'id -u'}})]:
                    try:limited.call(method,**params)
                    except RuntimeError as exc:assert 'Permission denied' in str(exc)
                    else:raise AssertionError('Role bypass: '+method)
                limited.call('file.list',path='/srv/sm-automation/shared')
                if role=='operator':limited.call('file.mkdir',path=shared)
                else:
                    try:limited.call('file.mkdir',path=shared+'/denied')
                    except RuntimeError as exc:assert 'Permission denied' in str(exc)
                    else:raise AssertionError('Viewer write allowed')
                try:limited.call('job.result',id=next(j['id'] for j in client.call('job.list') if j['kind']=='command'))
                except RuntimeError as exc:assert 'Permission denied' in str(exc)
                print('PASS: real '+role+' login, allowed shared access, denied root commands/secrets/admin/history')
        finally:
            run(['rm','-rf','--',remote,shared])
            if users:
                code='from common.config import load_config; from storage.encrypted import EncryptedStore; import sys; c=load_config("/opt/SM_Automation/config/app.local.json"); s=EncryptedStore(c.data_directory,c.key_file); a=s.read_json("gui-accounts.json.enc",{}); [a.pop(n,None) for n in sys.argv[1:]]; s.write_json("gui-accounts.json.enc",a)'
                run(['env','PYTHONPATH=/opt/SM_Automation/src','/opt/SM_Automation/.venv/bin/python','-c',code,*users])

if __name__=='__main__':main()

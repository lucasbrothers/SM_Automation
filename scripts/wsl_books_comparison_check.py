"""Local WSL acceptance for book execution, schedule CRUD and read-only backup comparison."""
import dataclasses
import ssl
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.config import load_config
from server.service import ManagementService,now
from server.main import TLSServer
from desktop.client import ServerClient,ConnectionSettings
from engine.ssh import SSHClient
from engine.remote import capture
from backup.profiles import unix_archive,LINUX_PATHS
from storage.encrypted import read_secret


def main():
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise SystemExit('Only approved local WSL')
    base=load_config('/opt/SM_Automation/config/app.local.json')
    identity=uuid.uuid4().hex;fixture=Path('/etc/cron.d')/('sm-compare-'+identity)
    try:
        fixture.write_text('# baseline comparison fixture\n');fixture.chmod(0o600)
        with tempfile.TemporaryDirectory(prefix='sm-books-check-') as directory:
            root=Path(directory);config=dataclasses.replace(base,data_directory=root/'DATA',backup_directory=root/'BACKUP',ssh_user='root',ssh_key_file=Path('/root/.ssh/sm_automation_wsl'),privilege='direct',ssh_profiles_file=root/'absent-profiles.json',max_workers=2)
            service=ManagementService(config)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(config.tls_cert,config.tls_key)
            token=read_secret(config.token_file);server=TLSServer(('127.0.0.1',0),service,context,token)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            client=ServerClient(ConnectionSettings('127.0.0.1',server.server_address[1],'/root/.config/sm-automation/ca.crt',token.decode()))
            try:
                inventory=[{'hostname':name,'ip':'127.0.0.1','os':'Ubuntu','profile':'default'} for name in ['lab-one','lab-two']]
                client.call('inventory.save',servers=inventory)
                book=client.call('equipment.book.save',name='통합 검증 장비록',hosts=['lab-one','lab-two'])
                def finish(job):
                    deadline=time.monotonic()+100
                    while job['status'] in {'queued','running'}:
                        if time.monotonic()>deadline:raise RuntimeError('Acceptance job timeout')
                        time.sleep(.1);job=client.call('job.get',id=job['id'])
                    return job,client.results(job['id'])
                job,rows=finish(client.call('job.start',kind='monitoring',equipment_book_id=book['id']))
                assert job['status']=='completed' and len(rows)==2 and job['equipment_book_id']==book['id']
                print('PASS: equipment book resolves two targets and executes through verified TLS',flush=True)
                schedule=client.call('schedule.create',kind='monitoring',hosts=[],equipment_book_id=book['id'],cron='*/5 * * * *',cron_timezone='Asia/Seoul',enabled=False)
                edited=client.call('schedule.update',id=schedule['id'],kind='connections',hosts=[],equipment_book_id=book['id'],cron='0 9 * * 1-5',cron_timezone='Asia/Seoul',enabled=False)
                assert edited['id']==schedule['id'] and edited['cron']=='0 9 * * 1-5'
                assert any(s['id']==edited['id'] for s in client.call('schedule.list'))
                client.call('equipment.book.save',id=book['id'],name=book['name'],hosts=['lab-one'])
                with service.scheduler.lock:
                    stored=service.scheduler.items[0];stored['enabled']=True;stored['next_run']=(datetime.now().astimezone()-timedelta(seconds=2)).isoformat()
                service.scheduler.tick();assert not service.scheduler.items[0]['enabled']
                print('PASS: schedule create/list/update preserves ID; changed equipment book pauses dispatch',flush=True)
                client.call('equipment.book.save',id=book['id'],name=book['name'],hosts=['lab-one','lab-two'])
                ssh=SSHClient('lab','127.0.0.1',user='root',key_filename=config.ssh_key_file)
                try:captured=capture(ssh,unix_archive(LINUX_PATHS),timeout=90,max_bytes=64*1024*1024)
                finally:ssh.close()
                assert captured.exit_code==0
                baseline_id=uuid.uuid4().hex;baseline_rows=[]
                for target in inventory:
                    path='acceptance/'+target['hostname']+'/configuration_files.tar.enc';service.backups.write_bytes(path,captured.stdout)
                    baseline_rows.append({**target,'status':'completed','result':{'artifacts':[{'name':'configuration_files','status':'completed','path':path}]}})
                baseline={'id':baseline_id,'kind':'backup','status':'completed','created_at':now(),'total':2,'done':2,'failed':0,'partial':0,'cancelled':0,'targets':inventory,'options':{},'results':baseline_rows}
                service.jobs[baseline_id]=baseline;service._save(baseline)
                fixture.write_text('# changed comparison fixture\n')
                compared,rows=finish(client.call('job.start',kind='backup_compare',equipment_book_id=book['id'],options={'baseline_job_id':baseline_id}))
                assert compared['status']=='completed' and len(rows)==2,(compared,rows)
                for row in rows:
                    assert row['result']['changed']>=1 and row['result']['files']==[]
                    page=client.call('backup.comparison',job_id=compared['id'],hostname=row['hostname'],limit=100)
                    changed=next(f for f in page['items'] if f['path']==str(fixture))
                    assert changed['status']=='changed' and '+# changed comparison fixture' in changed['diff']
                print('PASS: whole-book baseline/current comparison detects actual config changes; summary and details paginated',flush=True)
                client.call('schedule.change',id=schedule['id'],delete=True);client.call('equipment.book.delete',id=book['id'])
            finally:server.shutdown();thread.join();server.server_close();service.close()
    finally:fixture.unlink(missing_ok=True)

if __name__=='__main__':main()

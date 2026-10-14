"""CI acceptance restricted to local WSL; uses isolated encrypted asset storage."""
import dataclasses
import ssl
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.config import load_config
from server.service import ManagementService
from server.main import TLSServer
from desktop.client import ServerClient,ConnectionSettings
from storage.encrypted import read_secret


def main():
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Only approved local WSL')
    base=load_config('/opt/SM_Automation/config/app.local.json')
    with tempfile.TemporaryDirectory(prefix='sm-ci-check-') as directory:
        root=Path(directory)
        config=dataclasses.replace(base,data_directory=root/'DATA',backup_directory=root/'BACKUP',ssh_user='root',ssh_key_file=Path('/root/.ssh/sm_automation_wsl'),privilege='direct',ssh_profiles_file=root/'absent.json',max_workers=2)
        service=ManagementService(config)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(config.tls_cert,config.tls_key)
        token=read_secret(config.token_file);server=TLSServer(('127.0.0.1',0),service,context,token)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=ServerClient(ConnectionSettings('127.0.0.1',server.server_address[1],'/root/.config/sm-automation/ca.crt',token.decode()))
        try:
            hosts=['ci-lab-one','ci-lab-two']
            client.call('inventory.save',servers=[{'hostname':h,'ip':'127.0.0.1','os':'Ubuntu'} for h in hosts])
            book=client.call('equipment.book.save',name='CI acceptance',hosts=hosts)
            client.call('ci.update',hosts=hosts,patch={'customer':'Acceptance','operational_status':'운영','service_name':'CI test'})
            job=client.call('job.start',kind='ci_inventory',equipment_book_id=book['id'])
            deadline=time.monotonic()+120
            while job['status'] in {'queued','running'}:
                if time.monotonic()>deadline:raise RuntimeError('CI acceptance timeout')
                time.sleep(.1);job=client.call('job.get',id=job['id'])
            assert job['status']=='completed',job
            rows=client.call('ci.list',query='Acceptance')['rows']
            assert len(rows)==2
            for row in rows:
                observed=row['observed']
                assert observed['actual_hostname'] and observed['os_name'] and observed['cpu_model'], observed
                assert observed['allocated_cpus']>0 and observed['allocated_memory_gib']>0 and observed['uptime_seconds']>0
                assert row['manual']['service_name']=='CI test' and row['last_success']
                assert 'result_ref' in service.jobs[job['id']]['results'][0]
            client.call('ci.update',hosts=[hosts[0]],patch={'owner':'Individual owner'})
            service.ci_registry().observe({'hostname':hosts[0],'ip':'127.0.0.1'},error='Synthetic connection failure')
            failed=client.call('ci.list',hosts=[hosts[0]])['rows'][0]
            assert failed['collection_status']=='failed' and failed['observed']['cpu_model'] and failed['manual']['owner']=='Individual owner'
            print('PASS: real local WSL SSH -> TLS CI discovery for equipment book, hardware/OS/CPU/memory/uptime; bulk+individual metadata; failed refresh preserves last successful inventory',flush=True)
        finally:
            server.shutdown();thread.join();server.server_close();service.close()

if __name__=='__main__':main()

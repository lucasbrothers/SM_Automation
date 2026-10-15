"""WSL-only acceptance using the compiled Windows binary in synthetic protocol mode.
Does not install a Windows service, inspect Windows hardware or modify OS settings.
"""
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.config import load_config
from storage.encrypted import read_secret
from server.service import ManagementService
from server.main import TLSServer
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from shared.agent_installer import bind_installer


def main():
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise SystemExit('Only approved local WSL')
    repo=Path(__file__).resolve().parents[1];exe=repo/'release/SM.Agent.exe'
    base=load_config('/opt/SM_Automation/config/app.local.json')
    fixture=repo/'logs'/('agent-acceptance-'+uuid.uuid4().hex);fixture.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix='sm-agent-server-') as temporary:
            root=Path(temporary);config=dataclasses.replace(base,data_directory=root/'DATA',backup_directory=root/'BACKUP',ssh_profiles_file=root/'absent.json')
            service=ManagementService(config)
            service.agents.configure({'enabled':True,'networks':['127.0.0.1/32','172.16.0.0/12','192.168.0.0/16','10.0.0.0/8'],'hours':1,'max_new':10})
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(config.tls_cert,config.tls_key)
            server=TLSServer(('0.0.0.0',0),service,context,read_secret(config.token_file));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                host=subprocess.check_output(['hostname','-I'],text=True).split()[0]
                certificate=x509.load_pem_x509_certificate(config.tls_cert.read_bytes());pin=certificate.fingerprint(hashes.SHA256()).hex()
                (fixture/'connection.json').write_text(json.dumps({'host':host,'port':server.server_address[1],'sha256':pin}),encoding='utf-8')
                folder=subprocess.check_output(['wslpath','-w',str(fixture)],text=True).strip()
                def run(mode):
                    outcome=subprocess.run([str(exe),'--protocol-test',folder,mode],capture_output=True,text=True,timeout=60)
                    assert outcome.returncode==0,(mode,outcome.returncode,outcome.stderr,outcome.stdout)
                    return outcome.stdout
                settings=json.loads((fixture/'connection.json').read_text())
                (fixture/'connection.json').write_text(json.dumps({**settings,'sha256':'0'*64}),encoding='utf-8')
                denied_pin=subprocess.run([str(exe),'--protocol-test',folder,'enroll'],capture_output=True,timeout=60)
                assert denied_pin.returncode!=0 and service.inventory()==[]
                (fixture/'connection.json').write_text(json.dumps(settings),encoding='utf-8')
                run('enroll')
                inventory=service.inventory();assert len(inventory)==1 and inventory[0]['transport']=='agent'
                identity=inventory[0]['agent_id'];hostname=inventory[0]['hostname']
                ci=service.dispatch('ci.list',{})['rows'][0]
                assert ci['observed']['smt_enabled']=='켜짐'
                # Existing agent authentication keeps working with new registration closed.
                service.agents.configure({'enabled':False,'networks':['127.0.0.1/32'],'hours':1,'max_new':10})
                run('enroll');assert len(service.inventory())==1
                job=service.submit('command',[hostname],{'command':"Write-Output 'SM-agent-fixture'"})
                deadline=time.monotonic()+5
                while not service.agents.read_tasks(identity):
                    assert time.monotonic()<deadline;time.sleep(.05)
                run('task')
                deadline=time.monotonic()+10
                while service.jobs[job['id']]['status'] in {'queued','running'}:
                    assert time.monotonic()<deadline;time.sleep(.05)
                completed=service.jobs[job['id']]
                assert completed['status']=='completed',completed
                assert 'SM-agent-fixture' in completed['results'][0]['result']['stdout']
                run('uninstall');assert service.agents.listing()[0]['status']=='uninstalled'
                service.agents.revoke(identity,remove=True)
                assert service.inventory()==[] and service.agents.listing()==[]
                denied=subprocess.run([str(exe),'--protocol-test',folder,'enroll'],capture_output=True,timeout=60)
                assert denied.returncode!=0
                # Distribution file includes only this server's PUBLIC certificate fingerprint.
                target=repo/'release/windows-client-setup-wsl.exe'
                bind_installer(repo/'release/windows-client-base.exe',target,pin)
                print('PASS: compiled Windows agent -> local WSL TLS signed auto-registration, CI, polling, PowerShell fixture result, uninstall notification and permanent revocation; no Windows service installed',flush=True)
            finally:server.shutdown();thread.join();server.server_close();service.close()
    finally:
        assert fixture.resolve().parent==(repo/'logs').resolve()
        shutil.rmtree(fixture)

if __name__=='__main__':main()

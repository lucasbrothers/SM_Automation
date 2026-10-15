"""Read-only backup acceptance limited to the approved local WSL loopback target."""
import dataclasses,json,sys,tempfile,time,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.config import load_config
from storage.encrypted import EncryptedStore
from server.service import ManagementService


def main():
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise SystemExit('Only local WSL')
    base=load_config('/opt/SM_Automation/config/app.local.json')
    source=EncryptedStore(Path("/opt/SM_Automation/DATA"),base.key_file)
    addresses={'127.0.0.1',*subprocess.check_output(['hostname','-I'],text=True).split()}
    target=next(r for r in source.read_json('inventory.json.enc',[]) if r['hostname']=='wsl-ubuntu' and r['ip'] in addresses)
    target={**target,'ip':'127.0.0.1'}
    with tempfile.TemporaryDirectory(prefix='sm-backup-check-') as directory:
        config=dataclasses.replace(base,data_directory=Path(directory)/'DATA',backup_directory=Path(directory)/'BACKUP')
        service=ManagementService(config)
        try:
            service.data.write_json('inventory.json.enc',[target])
            credentials=source.read_json('client-credentials.json.enc',{})
            service.data.write_json('client-credentials.json.enc',{'wsl-ubuntu':{**credentials.get('wsl-ubuntu',{}),'ip':'127.0.0.1'}})
            job=service.submit('backup',['wsl-ubuntu'])
            deadline=time.monotonic()+600
            while service.jobs[job['id']]['status'] in {'queued','running'} and time.monotonic()<deadline:time.sleep(.5)
            current=service.jobs[job['id']]
            output={'status':current['status'],'targets':[]}
            for saved in current['results']:
                row=service._result(saved)
                output['targets'].append({'hostname':row['hostname'],'status':row['status'],'error':row.get('error'),'artifacts':[{k:a.get(k) for k in ('name','status','exit_code','errors','error')} for a in row.get('result',{}).get('artifacts',[])]})
                for artifact in row.get('result',{}).get('artifacts',[]):
                    if artifact.get('status')=='completed':assert service.backups.read_bytes(artifact['path']) is not None
            if current['status']=='completed':
                comparison=service.submit('backup_compare',['wsl-ubuntu'],{'baseline_job_id':job['id']})
                deadline=time.monotonic()+180
                while service.jobs[comparison['id']]['status'] in {'queued','running'} and time.monotonic()<deadline:time.sleep(.2)
                output['comparison_status']=service.jobs[comparison['id']]['status']
                assert output['comparison_status']=='completed'
            print(json.dumps(output,ensure_ascii=False))
            if current['status']!='completed':raise SystemExit(1)
        finally:service.close()


if __name__=='__main__':main()

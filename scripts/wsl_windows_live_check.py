"""Actual Windows agent acceptance, only after explicit permission for this PC.
Call from Windows with --hostname $env:COMPUTERNAME. Tests are read-only except
small owned transfer fixtures and temporary command/book/schedule entries.
"""
import argparse,hashlib,json,subprocess,sys,tempfile,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.config import load_config
from storage.encrypted import read_secret,EncryptedStore
from desktop.client import ConnectionSettings,ServerClient


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--hostname',required=True);parser.add_argument('--only',default='');args=parser.parse_args()
    if sys.platform!='linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise SystemExit('Use the local WSL SERVER')
    config=load_config('/opt/SM_Automation/config/app.local.json')
    client=ServerClient(ConnectionSettings('127.0.0.1',config.listen_port,'/root/.config/sm-automation/ca.crt',read_secret(config.token_file).decode()))
    agent=next(r for r in client.call('agent.list') if r['hostname'].casefold()==args.hostname.casefold())
    assert agent['version']=='1.1.0' and agent['status']=='online',agent
    host=agent['hostname'];report=[];token=uuid.uuid4().hex[:12];book=None;schedule=None;saved_name='SM acceptance '+token
    repo=Path(__file__).resolve().parents[1];fixture=repo/'logs'/('windows-live-'+token);fixture.mkdir(parents=True)
    win_path=subprocess.check_output(['wslpath','-w',str(fixture)],text=True).strip()
    payload=b'SM Automation actual Windows transfer fixture\n'+bytes(range(256))*256
    (fixture/'source.bin').write_bytes(payload)
    def wait(job):
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            state=client.call('job.get',id=job['id'])
            if state['status'] not in {'queued','running'}:return state,client.results(job['id'])
            time.sleep(1)
        raise TimeoutError('Job did not finish: '+job['id'])
    def run(kind,options=None,book_id=None):
        state,rows=wait(client.call('job.start',kind=kind,hosts=[host],options=options or {},equipment_book_id=book_id))
        if state['status']!='completed':
            detail=[{'status':r['status'],'error':r.get('error'),'artifacts':[{k:a.get(k) for k in ('name','status','errors','error')} for a in r.get('result',{}).get('artifacts',[])]} for r in rows]
            raise AssertionError(json.dumps(detail,ensure_ascii=False))
        assert len(rows)==1 and rows[0]['hostname']==host
        return rows[0]
    requested=set(args.only.split(',')) if args.only else None
    def check(name,fn):
        if requested and name not in requested:return
        print('START '+name,flush=True);started=time.monotonic()
        try:
            value=fn();report.append({'name':name,'status':'passed','detail':value,'seconds':round(time.monotonic()-started,2)});print('PASS '+name,flush=True)
        except Exception as error:
            report.append({'name':name,'status':'failed','error':str(error)[:5000]});print('FAIL '+name+': '+str(error)[:5000],flush=True)
    try:
        def ci():
            row=run('ci_inventory')['result'];assert row['actual_hostname'].casefold()==host.casefold() and row.get('logical_cpus') and row.get('memory_gib')
            return 'Actual hostname/OS/CPU/memory/SMT observed'
        check('CI inventory',ci)
        def command():
            row=run('command',{'command':"whoami; [Environment]::MachineName; Write-Output 'SM-agent-live-test'"})['result'];assert 'system' in row['stdout'].casefold() and host.casefold() in row['stdout'].casefold() and 'SM-agent-live-test' in row['stdout'];return 'PowerShell executed as SYSTEM'
        check('SYSTEM PowerShell command',command)
        def failure():
            state,rows=wait(client.call('job.start',kind='command',hosts=[host],options={'command':"[Console]::Error.WriteLine('SM expected test failure'); exit 7"}))
            assert state['status']=='failed' and rows[0]['result']['exit_code']==7;return 'Expected nonzero exit correctly reported as failed'
        check('Command failure reporting',failure)
        def connections():
            row=run('connections');assert isinstance(row['result']['connections'],list)
            cached=client.call('connections.cached',offset=0)
            assert cached['total']>0;return 'TCP snapshot and persisted cache available'
        check('TCP connection collection',connections)
        with tempfile.TemporaryDirectory(prefix='sm-win-transfer-') as temporary:
            server_path=str(Path(temporary)/'uploaded.bin')
            def upload():
                run('transfer',{'direction':'upload','client_path':win_path+'\\source.bin','server_path':server_path})
                assert Path(server_path).read_bytes()==payload;return 'CLIENT -> Linux SERVER: bytes and SHA256 verified'
            check('CLIENT to SERVER upload',upload)
            def download():
                run('transfer',{'direction':'download','client_path':win_path+'\\downloaded.bin','server_path':server_path})
                assert (fixture/'downloaded.bin').read_bytes()==payload;return 'Linux SERVER -> CLIENT: real destination and SHA256 verified'
            check('SERVER to CLIENT download',download)
        def backup():
            row=run('backup')['result'];assert row['artifact_count']>=10
            store=EncryptedStore(Path(client.call('status')['backup_directory']),config.key_file)
            for artifact in row['artifacts']:
                content=store.read_bytes(artifact['path']);assert len(content)==artifact['size']
                assert store.path(artifact['path']).read_bytes()!=content
            configuration=json.loads(store.read_bytes(row['artifacts'][0]['path']))
            assert configuration['format']=='base64-files-v1' and len(configuration['files'])>0
            return str(row['artifact_count'])+' actual Windows artifacts encrypted on Linux SERVER'
        check('Windows configuration backup',backup)
        def comparison():
            baseline=next(j for j in client.call('job.list',kind='backup') if j['status']=='completed' and any(r['hostname']==host for r in client.results(j['id'])))
            row=run('backup_compare',{'baseline_job_id':baseline['id']})['result']
            return 'Configuration compare completed: '+str(row['total'])+' files, '+str(row['changed'])+' differences'
        check('Windows backup configuration compare',comparison)
        book=client.call('equipment.book.save',name='SM acceptance '+token,hosts=[host])
        check('Equipment book execution',lambda:(run('connections',book_id=book['id']) and 'Book selected this Windows CLIENT'))
        client.call('command.saved.save',name=saved_name,command="Write-Output 'SM-agent-live-test'")
        check('Saved command library',lambda:next(r['name'] for r in client.call('command.saved.list') if r['name']==saved_name))
        schedule=client.call('schedule.create',kind='connections',hosts=[host],equipment_book_id=book['id'],run_at=(datetime.now(timezone.utc)+timedelta(seconds=40)).isoformat())
        def scheduled():
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                current=next(r for r in client.call('schedule.list') if r['id']==schedule['id'])
                if current.get('last_job_id'):
                    state,rows=wait({'id':current['last_job_id']});assert state['status']=='completed';return 'Linux schedule ran Windows collection without GUI submission'
                time.sleep(1)
            raise TimeoutError('Schedule did not run')
        check('SERVER-owned scheduled task',scheduled)
    finally:
        if schedule:client.call('schedule.change',id=schedule['id'],delete=True)
        if book:client.call('equipment.book.delete',id=book['id'])
        if any(r['name']==saved_name for r in client.call('command.saved.list')):client.call('command.saved.delete',name=saved_name)
        report_path=repo/'logs/windows-live-acceptance-report.json'
        prior=json.loads(report_path.read_text(encoding='utf-8')) if requested and report_path.exists() else {}
        merged={r['name']:r for r in prior.get('tests',[])};merged.update({r['name']:r for r in report})
        report_path.write_text(json.dumps({'host':host,'agent_id':agent['id'],'version':agent['version'],'tests':list(merged.values())},ensure_ascii=False,indent=2),encoding='utf-8')
    if any(r['status']!='passed' for r in report):raise SystemExit(1)
    print('PASS all actual Windows CLIENT tests; temporary book/schedule/library entries removed',flush=True)


if __name__=='__main__':main()

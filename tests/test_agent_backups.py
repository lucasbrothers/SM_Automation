import base64,json,threading
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from storage.encrypted import EncryptedStore
from test_windows_agents import service,Device,opened


@dataclass
class Config:
    max_capture_mb:int=64
    backup_timeout:int=180
    privilege:str='direct'


def setup(service,tmp_path):
    opened(service);device=Device(service);device.exchange(version='1.1.0')
    row=service.inventory()[0]
    service.config=Config();service.backups=EncryptedStore(tmp_path/'BACKUP',service.data.root.parent/'master')
    service.heavy_slots=threading.Semaphore(1);service._progress=lambda *args:None
    return row


def test_windows_agent_backups_store_real_encrypted_artifacts(service,tmp_path,monkeypatch):
    row=setup(service,tmp_path);calls=[]
    def execute(job,target):
        assert job['kind']=='backup_artifact';script=job['options']['script'];calls.append(script)
        text=json.dumps({'format':'base64-files-v1','files':[{'path':'C:\\Windows\\hosts','content':base64.b64encode(b'fixture').decode()}],'errors':[]}) if 'base64-files-v1' in script else 'fixture output'
        return {'status':'completed','result':{'stdout':text,'stderr':'','exit_code':0}}
    monkeypatch.setattr(service.agents,'execute',execute)
    result=service.agents.backup({'id':'a'*32},row)
    assert result['status']=='completed' and len(calls)>=10
    artifacts=result['result']['artifacts'];config=artifacts[0]
    assert config['name']=='configuration_files'
    assert json.loads(service.backups.read_bytes(config['path']))['format']=='base64-files-v1'
    assert all(service.backups.read_bytes(a['path']) for a in artifacts)
    assert any('2MB' in script for script in calls)


def test_windows_agent_backup_failure_is_partial_not_false_success(service,tmp_path,monkeypatch):
    row=setup(service,tmp_path)
    def execute(job,target):
        denied='base64-files-v1' in job['options']['script']
        return {'status':'failed' if denied else 'completed','result':{'stdout':'fixture','stderr':'Access denied' if denied else '', 'exit_code':1 if denied else 0}}
    monkeypatch.setattr(service.agents,'execute',execute)
    result=service.agents.backup({'id':'b'*32},row)
    assert result['status']=='partial'
    assert result['result']['artifacts'][0]['errors']==['Access denied']


def test_old_windows_client_requires_update_explicitly(service,tmp_path):
    row=setup(service,tmp_path);record=service.agents.device(row['agent_id']);record['version']='1.0.0'
    with pytest.raises(ValueError,match='1.1.0'):service.agents.backup({'id':'c'*32},row)


def test_backup_root_password_is_ephemeral_and_never_in_job_options(service,tmp_path):
    row=setup(service,tmp_path)
    service.history_errors=[];service.command_passwords={};service.pool=Mock();service.summary=lambda job:job
    response=service.submit('backup',[row['hostname']],{'root_password':'synthetic-backup-secret'})
    assert response['options']=={}
    saved=service.data.read_json('jobs/'+response['id']+'.json.enc')
    assert 'synthetic-backup-secret' not in json.dumps(saved)
    assert service.command_passwords[response['id']]=='synthetic-backup-secret'


def test_backup_next_artifact_is_offered_in_same_ack_without_idle_poll(service,tmp_path):
    import time
    row=setup(service,tmp_path)
    device=Device(service);device.exchange(version='1.1.0');row=next(r for r in service.inventory() if r['agent_id']==device.id)
    job={'id':'d'*32,'kind':'backup_artifact','options':{'script':"Write-Output 'first'"}}
    service.jobs[job['id']]={'status':'running'}
    task_id=service.agents.prepare(job,row)
    assert device.exchange(version='1.1.0')['task']['id']==task_id
    def next_task():
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            with service.lock:
                if service.data.read_json('agents/results/'+task_id+'.json.enc'):
                    service.agents.prepare({**job,'options':{'script':"Write-Output 'second'"}},row);return
            time.sleep(.01)
    worker=threading.Thread(target=next_task);worker.start()
    reply=device.exchange(version='1.1.0',results=[{'id':task_id,'status':'completed','result':{'stdout':'first','stderr':'','exit_code':0}}])
    worker.join(2)
    assert reply['ack']==[task_id] and reply['task']['options']['script']=="Write-Output 'second'"


def test_windows_agent_configuration_compare_reads_complete_encrypted_baseline(service,tmp_path,monkeypatch):
    row=setup(service,tmp_path);changed=False
    def execute(job,target):
        if 'base64-files-v1' in job['options']['script']:
            text=json.dumps({'format':'base64-files-v1','files':[{'path':'C:/Windows/hosts','content':base64.b64encode(b'new hosts' if changed else b'old hosts').decode()}],'errors':[]})
        else:text='fixture output'
        return {'status':'completed','result':{'stdout':text,'stderr':'','exit_code':0}}
    monkeypatch.setattr(service.agents,'execute',execute)
    baseline=service.agents.backup({'id':'e'*32},row)
    service.jobs['e'*32]={'results':[baseline]};changed=True
    result=service.agents.compare_backup({'id':'f'*32,'options':{'baseline_job_id':'e'*32}},row)
    assert result['status']=='completed' and result['result']['changed']==1
    report=service.backups.read_json(result['result']['report_path'])
    assert report['files'][0]['status']=='changed'

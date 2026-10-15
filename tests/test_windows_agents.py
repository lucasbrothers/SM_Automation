import base64
import json
import threading
import time
import sys
import uuid
from types import SimpleNamespace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from storage.encrypted import EncryptedStore
from server.agents import AgentManager
from server.service import ManagementService
from server.auth import authorize


@pytest.fixture
def service(tmp_path):
    key=tmp_path/'master';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    instance=ManagementService.__new__(ManagementService);instance.data=EncryptedStore(tmp_path/'DATA',key)
    instance.lock=threading.RLock();instance.jobs={};instance.closed=False
    instance.agents=AgentManager(instance)
    return instance


class Device:
    def __init__(self,service,name='win-client'):
        self.service=service;self.id=uuid.uuid4().hex;self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048);self.name=name
        public=self.key.public_key().public_numbers()
        self.public={'modulus':base64.b64encode(public.n.to_bytes(256,'big')).decode(),'exponent':base64.b64encode(public.e.to_bytes(3,'big')).decode()}
    def hello(self,peer='127.0.0.1'):
        return self.service.agents.rpc('agent.hello',{'device_id':self.id,'public_key':self.public},peer)
    def signed(self,challenge,**values):
        payload=json.dumps({'device_id':self.id,'hostname':self.name,'version':'fixture',**values},ensure_ascii=False)
        text=('SM-AUTOMATION-AGENT-v1\n'+challenge['challenge_id']+'\n'+challenge['nonce']+'\n'+payload).encode()
        signature=self.key.sign(text,padding.PKCS1v15(),hashes.SHA256())
        return {'challenge_id':challenge['challenge_id'],'payload':payload,'signature':base64.b64encode(signature).decode()}
    def exchange(self,**values):
        return self.service.agents.rpc('agent.exchange',self.signed(self.hello(),**values),'127.0.0.1')


def opened(service):
    service.agents.configure({'enabled':True,'networks':['127.0.0.1/32'],'hours':1,'max_new':1000})


def test_auto_registration_signed_ci_preserves_existing_target(service):
    opened(service)
    service.data.write_json('inventory.json.enc',[{'hostname':'win-client','ip':'10.0.0.2','os':'Linux','profile':'default'}])
    device=Device(service)
    response=device.exchange(observation={'actual_hostname':'win-client','primary_ip':'127.0.0.1','cpu_topology':[{'cores':2,'logical':4}],'cpu_model':'Sample CPU','os_name':'Windows'})
    assert response['hostname']!='win-client'
    rows=service.inventory();assert len(rows)==2 and rows[0]['os']=='Linux'
    assert rows[1]['transport']=='agent' and rows[1]['agent_status']=='online'
    ci=service.dispatch('ci.list',{'hosts':[response['hostname']]})['rows'][0]
    assert ci['observed']['smt_enabled']=='켜짐'
    service.dispatch('ci.update',{'hosts':[response['hostname']],'patch':{'customer':'Acme'}})
    device.exchange(observation={'actual_hostname':'win-client','primary_ip':'127.0.0.2','cpu_model':'Updated'})
    assert service.dispatch('ci.list',{'hosts':[response['hostname']]})['rows'][0]['manual']['customer']=='Acme'


def test_closed_network_policy_and_expired_policy_keep_known_devices(service):
    device=Device(service)
    with pytest.raises(ValueError):device.hello()
    opened(service)
    with pytest.raises(ValueError):device.hello('192.0.2.3')
    device.exchange()
    service.agents.policy['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert device.exchange()['hostname']==device.name
    with pytest.raises(ValueError):Device(service).hello()


def test_challenge_is_single_use_and_invalid_signature_cannot_enroll(service):
    opened(service);device=Device(service)
    challenge=device.hello();params=device.signed(challenge)
    bad={**params,'signature':base64.b64encode(b'x'*256).decode()}
    with pytest.raises(ValueError):service.agents.rpc('agent.exchange',bad,'127.0.0.1')
    assert service.inventory()==[]
    with pytest.raises(ValueError):service.agents.rpc('agent.exchange',params,'127.0.0.1')
    challenge=device.hello();params=device.signed(challenge);params['payload']+=' '
    with pytest.raises(ValueError):service.agents.rpc('agent.exchange',params,'127.0.0.1')
    device.exchange()
    impostor=Device(service);impostor.id=device.id
    with pytest.raises(ValueError):impostor.hello()


def test_lifecycle_offline_uninstall_remove_revokes_identity(service):
    opened(service);device=Device(service);device.exchange()
    record=service.agents.device(device.id)
    record['last_seen']=(datetime.now(timezone.utc)-timedelta(seconds=121)).isoformat()
    assert service.agents.listing()[0]['status']=='offline'
    device.exchange(uninstall=True)
    assert service.agents.listing()[0]['status']=='uninstalled'
    with pytest.raises(ValueError):device.hello()
    assert len(service.inventory())==1
    service.agents.revoke(device.id,remove=True)
    assert service.inventory()==[] and service.agents.listing()==[]
    with pytest.raises(ValueError):device.hello()
    # Persisted revocation survives SERVER restart; identity cannot silently reappear.
    restored=AgentManager(service)
    with pytest.raises(ValueError):restored.rpc('agent.hello',{'device_id':device.id,'public_key':device.public},'127.0.0.1')


def test_device_tasks_signed_result_idempotence_and_no_cross_device_result(service):
    opened(service);device=Device(service);device.exchange();other=Device(service,'other');other.exchange()
    row=service.inventory()[0]
    job={'id':uuid.uuid4().hex,'kind':'command','status':'running','options':{'command':'Write-Output fixture'},'cancel_requested':False}
    service.jobs[job['id']]=job
    with service.lock:task_id=service.agents.prepare(job,row)
    assert device.exchange()['task']['id']==task_id
    # Another device cannot complete this task.
    other.exchange(results=[{'id':task_id,'status':'completed','result':{'stdout':'forged'}}])
    assert not service.data.path('agents/results/'+task_id+'.json.enc').exists()
    result={'id':task_id,'status':'completed','result':{'stdout':'fixture','stderr':'','exit_code':0}}
    assert task_id in device.exchange(results=[result])['ack']
    assert task_id in device.exchange(results=[result])['ack']
    completed=service.agents.execute(job,row)
    assert completed['status']=='completed' and completed['result']['stdout']=='fixture'


def test_cancelled_task_not_delivered_and_deleted_inventory_does_not_reenroll(service):
    opened(service);device=Device(service);device.exchange();row=service.inventory()[0]
    job={'id':uuid.uuid4().hex,'kind':'command','status':'running','options':{'command':'Never run'},'cancel_requested':True}
    service.jobs[job['id']]=job
    with service.lock:service.agents.prepare(job,row)
    assert device.exchange()['task'] is None
    service.data.write_json('inventory.json.enc',[])
    with pytest.raises(ValueError):device.exchange()
    assert service.inventory()==[]


def test_agent_admin_permissions():
    authorize('viewer','agent.list',{})
    for method in ['agent.policy.save','agent.revoke','agent.server_identity']:
        with pytest.raises(ValueError):authorize('operator',method,{})


def test_server_bound_installer_has_public_fingerprint_only(tmp_path):
    from shared.agent_installer import bind_installer
    source=tmp_path/'base.exe';source.write_bytes(b'MZ\0fixture')
    target=tmp_path/'setup.exe';bind_installer(source,target,'a'*64)
    assert b'"sha256":"'+b'a'*64+b'"' in target.read_bytes()
    assert Path(str(target)+'.sha256').exists()
    with pytest.raises(ValueError):bind_installer(source,source,'b'*64)

def test_interrupted_auto_registration_recovers_without_duplicate(service,monkeypatch):
    opened(service);device=Device(service)
    original=service.data.write_json;failed=[]
    def write(name,value):
        if name=='agents/bindings.json.enc' and not failed:
            failed.append(True);raise OSError('Synthetic disk interruption')
        return original(name,value)
    monkeypatch.setattr(service.data,'write_json',write)
    with pytest.raises(OSError):device.exchange()
    assert len(service.data.read_json('inventory.json.enc'))==1
    monkeypatch.setattr(service.data,'write_json',original)
    service.agents=AgentManager(service)
    device.exchange()
    assert len(service.inventory())==1 and service.inventory()[0]['agent_id']==device.id


def test_manual_inventory_removal_revokes_old_agent_identity(service):
    opened(service);device=Device(service);device.exchange();service.profiles={}
    service.save_inventory([])
    with pytest.raises(ValueError):device.hello()
    assert service.inventory()==[]


def test_unknown_device_ids_are_not_retained_in_cache(service):
    for _ in range(100):assert service.agents.device(uuid.uuid4().hex) is None
    assert not service.agents.cache

def test_missing_bound_device_registry_cannot_be_replaced_with_new_key(service):
    opened(service);device=Device(service);device.exchange()
    service.data.path('agents/devices/'+device.id+'.json.enc').unlink()
    service.agents=AgentManager(service)
    impostor=Device(service);impostor.id=device.id
    with pytest.raises(ValueError):impostor.hello()


@pytest.mark.skipif(sys.platform!="linux",reason="Linux SERVER filesystem semantics")
def test_agent_file_upload_verifies_checksum_and_creates_actual_file(service,tmp_path):
    import hashlib
    opened(service);device=Device(service);device.exchange();row=service.inventory()[0]
    path=tmp_path/'received.bin';content=b'actual agent transfer\x00'*100
    job={'id':uuid.uuid4().hex,'kind':'transfer','status':'running','options':{'direction':'upload','server_path':str(path),'client_path':'C:/Temp/source.bin'}}
    service.jobs[job['id']]=job
    with service.lock:task_id=service.agents.prepare(job,row)
    task=device.exchange()['task'];assert task['id']==task_id
    result={'id':task_id,'status':'completed','result':{'content':base64.b64encode(content).decode(),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}}
    device.exchange(results=[result])
    received=service.agents.execute(job,row)
    assert received['status']=='completed' and path.read_bytes()==content
    assert 'content' not in received['result']


@pytest.mark.skipif(sys.platform!="linux",reason="Linux SERVER filesystem semantics")
def test_agent_file_download_does_not_copy_file_into_every_queue(service,tmp_path):
    import hashlib
    opened(service);device=Device(service);device.exchange();row=service.inventory()[0]
    path=tmp_path/'source.bin';content=b'file body';path.write_bytes(content)
    job={'id':uuid.uuid4().hex,'kind':'transfer','status':'running','options':{'direction':'download','server_path':str(path),'client_path':'C:/Temp/new.bin'}}
    service.jobs[job['id']]=job
    with service.lock:task_id=service.agents.prepare(job,row)
    assert 'content' not in service.agents.read_tasks(device.id)[0]['options']
    task=device.exchange()['task']
    assert base64.b64decode(task['options']['content'])==content
    device.exchange(results=[{'id':task_id,'status':'completed','result':{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}}])
    assert service.agents.execute(job,row)['status']=='completed'


def test_long_poll_wakes_when_task_enqueued_without_holding_registry_lock(service):
    opened(service);device=Device(service);device.exchange()
    row=service.inventory()[0];response={};started=threading.Event()
    def poll():
        started.set();response.update(device.exchange(wait_for_task=True))
    thread=threading.Thread(target=poll);thread.start();assert started.wait(1)
    time.sleep(.1)
    job={'id':uuid.uuid4().hex,'kind':'command','status':'running','options':{'command':'Write-Output fixture'},'cancel_requested':False}
    with service.lock:
        service.jobs[job['id']]=job;task_id=service.agents.prepare(job,row)
    thread.join(2)
    assert not thread.is_alive()
    assert response['task']['id']==task_id and response['poll_seconds']==1
    assert 'received task' in job['message']

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from storage.encrypted import EncryptedStore
from server.equipment import change,get
from server.service import ManagementService


def test_equipment_book_supports_1000_hosts_and_edit(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600);store=EncryptedStore(tmp_path/'data',key)
    inventory=[{'hostname':'host-'+str(i)} for i in range(1000)];hosts=[r['hostname'] for r in inventory]
    row=change(store,'equipment.book.save',{'name':'전체 장비록','hosts':hosts},inventory)
    assert len(get(store,row['id'],inventory)['hosts'])==1000
    changed=change(store,'equipment.book.save',{'id':row['id'],'name':'수정 장비록','hosts':hosts[:500]},inventory)
    assert changed['id']==row['id'] and len(get(store,row['id'],inventory)['hosts'])==500
    with pytest.raises(ValueError):get(store,row['id'],inventory[:100])
    change(store,'equipment.book.delete',{'id':row['id']},inventory)
    with pytest.raises(ValueError):get(store,row['id'],inventory)

@pytest.mark.parametrize('kind,expected',[('connections',2),('backup_compare',1)])
def test_global_concurrency_and_heavy_work_limit(kind,expected):
    service=ManagementService.__new__(ManagementService);service.ssh_slots=threading.BoundedSemaphore(2);service.heavy_slots=threading.BoundedSemaphore(1)
    lock=threading.Lock();active=0;peak=0
    def work(job,row):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        time.sleep(.03)
        with lock:active-=1
        return {}
    service._target_inner=work
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda _:service._target({'kind':kind},{}),range(16)))
    assert peak==expected


def test_large_result_is_stored_separately_and_loaded_on_demand(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    service=ManagementService.__new__(ManagementService);service.data=EncryptedStore(tmp_path/'DATA',key)
    row={'hostname':'lab','ip':'127.0.0.1','status':'completed','result':{'payload':'x'*1000000}}
    stored=service._store_result({'id':'a'*32,'kind':'connections'},row)
    assert 'result' not in stored and 'result_ref' in stored
    loaded=service._result(stored)
    assert loaded.pop("observed_at") == stored["observed_at"]
    assert loaded==row


def test_successful_auth_hash_cache_and_password_change(tmp_path,monkeypatch):
    import server.auth as auth
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600);store=EncryptedStore(tmp_path/'DATA',key)
    auth.save_account(store,'tester','synthetic-old')
    original=auth.password_hash;calls=[]
    def counted(password,salt):calls.append(True);return original(password,salt)
    monkeypatch.setattr(auth,'password_hash',counted)
    assert auth.authenticate(store,'tester','synthetic-old') and auth.authenticate(store,'tester','synthetic-old')
    assert len(calls)==1
    auth.save_account(store,'tester','synthetic-new')
    assert not auth.authenticate(store,'tester','synthetic-old')

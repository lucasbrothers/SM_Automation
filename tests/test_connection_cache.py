import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from server.service import ManagementService
from server.auth import authorize


@pytest.fixture
def service(tmp_path,monkeypatch):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    config=SimpleNamespace(data_directory=tmp_path/'DATA',backup_directory=tmp_path/'BACKUP',key_file=key,ssh_profiles_file=tmp_path/'none')
    monkeypatch.setattr('server.service.Scheduler',lambda service:Mock())
    instance=ManagementService(config)
    instance.data.write_json('inventory.json.enc',[{'hostname':'lab','ip':'127.0.0.1','os':'Linux','profile':'default'}])
    instance.submit=Mock(side_effect=AssertionError('Cache must never submit remote work'))
    yield instance
    instance.close()


def save(instance,identity,stamp,status='completed',ip='127.0.0.1',legacy=False):
    row={'hostname':'lab','ip':ip,'os':'Linux','status':status,'result':{'connections':[]}}
    job={'id':identity,'kind':'connections','created_at':stamp,'finished_at':stamp,'status':status,'total':1,'done':1,'failed':int(status=='failed'),'results':[]}
    row=instance._store_result(job,row)
    if legacy:
        row.pop('observed_at',None)
        full=instance._result(row);full.pop('observed_at',None);instance.data.write_json(row['result_ref'],full)
    else:
        row['observed_at']=stamp
        full=instance._result(row);full['observed_at']=stamp;instance.data.write_json(row['result_ref'],full)
    job['results']=[row];instance.jobs[identity]=job;instance._save(job)


def test_cached_results_survive_restart_and_do_not_submit_remote_work(service):
    save(service,'old','2026-10-14T10:00:00+00:00')
    save(service,'new','2026-10-15T10:00:00+00:00')
    result=service.dispatch('connections.cached',{})
    assert result['items'][0]['observed_at']=='2026-10-15T10:00:00+00:00'
    assert not result['items'][0]['time_is_job_time']
    restored=ManagementService(service.config)
    try:assert restored.dispatch('connections.cached',{})==result
    finally:restored.close()
    service.submit.assert_not_called()
    assert service.dispatch('connections.cached',{'offset':1})['items']==[]


def test_latest_failure_and_legacy_time_are_honest_and_ip_change_not_reused(service):
    save(service,'first','2026-10-14T10:00:00+00:00',legacy=True)
    assert service.dispatch('connections.cached',{})['items'][0]['time_is_job_time']
    save(service,'failed','2026-10-15T10:00:00+00:00','failed')
    assert service.dispatch('connections.cached',{})['items'][0]['status']=='failed'
    service.data.write_json('inventory.json.enc',[{'hostname':'lab','ip':'127.0.0.2','os':'Linux'}])
    assert service.dispatch('connections.cached',{})['total']==0


@pytest.mark.parametrize('offset',[-1,True,'0',1.5])
def test_invalid_cache_offset(service,offset):
    with pytest.raises(ValueError):service.dispatch('connections.cached',{'offset':offset})


@pytest.mark.parametrize('role',['viewer','operator','admin'])
def test_cache_is_readable_by_query_roles(role):authorize(role,'connections.cached',{})

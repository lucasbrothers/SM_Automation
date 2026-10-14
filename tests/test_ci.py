from pathlib import Path
import threading
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from ci.registry import CIRegistry
from ci.collector import parse_linux, parse_sections, collect
from server.auth import authorize
from server.service import ManagementService
from storage.encrypted import EncryptedStore


@pytest.fixture
def registry(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    return CIRegistry(EncryptedStore(tmp_path/'data',key))


def test_manual_bulk_and_observation_failure_survive_restart(registry):
    hosts=[{'hostname':f'h{i}','ip':'127.0.0.1','os':'Linux'} for i in range(2)]
    result=registry.update(hosts,['h0','h1'],{'customer':'고객사','operational_status':'운영'})
    assert len(result['updated'])==2 and not result['failed']
    registry.observe(hosts[0],{'serial_number':'SERIAL','allocated_cpus':2})
    registry.update(hosts,['h0'],{'owner':'Alice'})
    registry.observe(hosts[0],error='SSH unavailable')
    reloaded=CIRegistry(registry.store)
    row=reloaded.listing(hosts,{})['rows'][0]
    assert row['manual']=={'customer':'고객사','operational_status':'운영','owner':'Alice'}
    assert row['observed']['serial_number']=='SERIAL' and row['last_success']
    assert row['collection_status']=='failed' and row['error']=='SSH unavailable'
    assert b'SERIAL' not in registry.store.path(registry.key('h0')).read_bytes()
    changed=[{**hosts[0],'ip':'127.0.0.2'}]
    assert reloaded.listing(changed,{})['rows'][0]['stale']


@pytest.mark.parametrize('patch',[{'observed':{}},{'owner':1},{'operational_status':'online'},{'purchase_date':'2026-02-30'},{'support_end':'26-01-01'}])
def test_metadata_validates_entire_bulk_patch_before_writing(registry,patch):
    with pytest.raises((ValueError,TypeError)):
        registry.update([{'hostname':'h'}],['h'],patch)
    assert registry.get('h')=={}


def test_filtered_pagination_1000_hosts_and_explicit_clear(registry):
    hosts=[{'hostname':f'h{i}','ip':'127.0.0.1','os':'Linux'} for i in range(1000)]
    registry.update(hosts,['h1','h2'],{'customer':'Acme','owner':'A'})
    registry.update(hosts,['h1'],{'owner':''})
    data=registry.listing(hosts,{'query':'acme','page_size':1,'offset':1})
    assert data['total']==2 and data['rows'][0]['hostname']=='h2'
    assert registry.listing(hosts,{'hosts':['h1']})['rows'][0]['manual']['owner']==''
    assert len(registry.listing(hosts,{'page_size':99999})['rows'])==200


def test_linux_does_not_confuse_guest_threads_with_physical_cores():
    raw={'actual_hostname':'lab','os_release':'NAME="Ubuntu"\nVERSION_ID="26.04"',
         'addresses':'10.0.0.2 10.0.0.3','cpuinfo':'model name : Sample CPU\nmodel name : Sample CPU',
         'logical_cpus':'16','affinity_cpus':'8','cpu_limit':'150000 100000','memory_limit':str(1024**3),
         'lscpu':'# comment\n0,0\n0,0\n1,0','meminfo':'MemTotal: 8388608 kB','uptime':'3600.50 0.1'}
    row=parse_linux(raw)
    assert row['logical_cpus']==16 and row['allocated_cpus']==1.5 and row['physical_cores']==2
    assert row['memory_gib']==8 and row['allocated_memory_gib']==1
    assert row['uptime_seconds']==3600.5 and row['primary_ip']=='10.0.0.2'
    assert row['gpu']=='미확인' and 'Serial' in row['warnings']
    assert row['cpu_model']=='Sample CPU' and row['os_version']=='26.04'


def test_sections_ignore_banners_and_do_not_evaluate_os_release():
    assert parse_sections('banner\nTOKEN:actual_hostname\nlab\nTOKEN:kernel\n6.0\n','TOKEN')=={'actual_hostname':'lab','kernel':'6.0'}
    assert parse_linux({'os_release':'NAME="$(touch /never)"'})['os_name']=='$(touch /never)'


def test_windows_cim_response_and_failures(monkeypatch):
    from engine.remote import CommandResult
    monkeypatch.setattr('ci.collector.capture',lambda *a,**k:CommandResult(b'{"actual_hostname":"win","os_name":"Windows","serial_number":"SN"}','',0))
    assert collect(Mock(),'windows')['serial_number']=='SN'
    monkeypatch.setattr('ci.collector.capture',lambda *a,**k:CommandResult(b'','Access denied',1))
    with pytest.raises(ValueError,match='CIM'):collect(Mock(),'windows')


def test_ci_roles_and_service_dispatch(registry):
    authorize('viewer','ci.list',{})
    authorize('operator','job.start',{'kind':'ci_inventory'})
    with pytest.raises(ValueError):authorize('viewer','ci.update',{})
    with pytest.raises(ValueError):authorize('operator','ci.update',{})
    service=ManagementService.__new__(ManagementService);service.data=registry.store;service.lock=threading.RLock()
    service.inventory=lambda:[{'hostname':'h','ip':'127.0.0.1','os':'Linux'}]
    service.dispatch('ci.update',{'hosts':['h'],'patch':{'service_name':'App'}})
    assert service.dispatch('ci.list',{})['rows'][0]['manual']['service_name']=='App'
    stored=service._store_result({'id':'a'*32,'kind':'ci_inventory'},{'hostname':'h','result':{'cpu_model':'CPU'},'status':'completed'})
    assert 'result_ref' in stored and service._result(stored)['result']['cpu_model']=='CPU'

def test_aix_partition_resources_and_uptime():
    from ci.collector import parse_aix
    row=parse_aix({'actual_hostname':'aix-lpar','primary_ip':'10.0.0.7','addresses':'127.0.0.1 10.0.0.7',
        'os_version':'7300-02-01','hardware_model':'IBM,9009','prtconf':'Machine Serial Number: SERIAL\nProcessor Type: PowerPC_POWER9\nNumber Of Processors: 4\nMemory Size: 16384 MB',
        'lpar':'Online Virtual CPUs : 8\nEntitled Capacity : 2.00','uptime':' 10:30AM up 3 days,  2:15, 2 users','boot_time':'system boot Oct 11 08:15'})
    assert row['allocated_cpus']==8 and row['physical_cores'] is None
    assert row['allocated_memory_gib']==16 and row['uptime_seconds']==3*86400+2*3600+15*60
    assert row['serial_number']=='SERIAL' and row['primary_ip']=='10.0.0.7'
    assert '2.00' in row['warnings'] and row['gpu']=='미확인'


def test_parent_cgroup_limits_apply_instead_of_unlimited_leaf():
    row=parse_linux({'logical_cpus':'16','affinity_cpus':'8','cpu_limit':'max 100000\n200000 100000\nmax 100000',
        'memory_limit':'max\n1073741824\n2147483648','meminfo':'MemTotal: 8388608 kB'})
    assert row['allocated_cpus']==2 and row['allocated_memory_gib']==1

def test_ci_sort_is_global_before_pagination_and_export_uses_same_order(registry):
    hosts=[{'hostname':'host'+str(i),'ip':'10.0.0.'+str(i+1),'os':'Linux'} for i in range(120)]
    for i,host in enumerate(hosts):
        registry.observe(host,{'allocated_cpus':120-i})
    page=registry.listing(hosts,{'sort_key':'allocated_cpus','page_size':10})
    assert page['rows'][0]['hostname']=='host119' and page['rows'][9]['observed']['allocated_cpus']==10
    page=registry.listing(hosts,{'sort_key':'allocated_cpus','page_size':10,'offset':100})
    assert page['rows'][0]['observed']['allocated_cpus']==101
    page=registry.listing(hosts,{'sort_key':'ip','descending':True,'page_size':1})
    assert page['rows'][0]['ip']=='10.0.0.120'
    with pytest.raises(ValueError):registry.listing(hosts,{'sort_key':'not-an-attribute'})

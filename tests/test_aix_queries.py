from pathlib import Path
from unittest.mock import Mock
import pytest
from engine.remote import CommandResult
from monitoring import aix
from server.service import ManagementService

ACCOUNTS="""root:
        id=0
        pgrp=system
        groups=system,bin,sys
        home=/
        shell=/usr/bin/ksh
        gecos=System: administrator
        account_locked=false
        expires=0
svc:
        id=210
        pgrp=staff
        groups=staff
        home=/home/svc
        shell=/usr/bin/ksh
        gecos=Service User
        account_locked=true
        expires=1231235926
"""
FILESETS="""#Path:Fileset:Level:State:PTF Id:Fix State:Type:Description:Destination Dir.
/usr/lib/objrepos:bos.rte:7.2.5.0:COMMITTED:::I:Base Operating System Runtime:
/etc/objrepos:bos.rte:7.2.5.0:COMMITTED:::I:Base Operating System Runtime:
"""
MEMORY=""" 2097152 memory pages
 131072 free pages
 20000 pinned pages
"""
FS="Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/hd4 1048576 419430 629146 40% /\n"
UPTIME=" 10:30AM up 3 days, 2:14, 2 users, load average: 0.25, 1.20, 2.30\n"

def test_accounts_preserve_colon_groups_and_locked_status_without_passwords():
    rows=aix.parse_accounts(ACCOUNTS)
    assert rows[0]["comment"]=="System: administrator"
    assert rows[0]["enabled"] is True and rows[1]["enabled"] is False
    assert rows[0]["groups"]=="system,bin,sys"
    assert all("password" not in r for r in rows)
    with pytest.raises(ValueError):aix.parse_accounts("bad response")

def test_installed_filesets_include_repository_not_candidate_versions():
    rows=aix.parse_filesets(FILESETS)
    assert len(rows)==2 and rows[0]["installed"]=="7.2.5.0"
    assert rows[0]["source"]!=rows[1]["source"]
    assert rows[0]["candidate"]=="COMMITTED"
    with pytest.raises(ValueError):aix.parse_filesets("unexpected")

def test_interim_fix_list_and_empty_and_bad_output():
    rows=aix.parse_fixes("ID STATE INSTALL TIME EFIX LABEL\n1 S 10/15/26 10:20:00 IJ12345s1a\n")
    assert rows[0]["name"]=="IJ12345s1a" and rows[0]["type"]=="interim_fix"
    assert aix.parse_fixes("There is no efix data on this system.")==[]
    with pytest.raises(ValueError):aix.parse_fixes("denied")

def test_resources_physical_pages_and_posix_df():
    result=aix.parse_resources(UPTIME,MEMORY,FS)
    assert result["load_average"]==[.25,1.2,2.3]
    assert result["memory_mb"]=={"total":8192,"free":512,"used":7680}
    assert result["root_filesystem"]["capacity"]=="40%"
    assert result["uptime"]=="3 days, 2:14"

@pytest.mark.parametrize("up,mem,fs",[("garbage",MEMORY,FS),(UPTIME,"2097152 memory pages",FS),(UPTIME,"2 memory pages\n3 free pages",FS),(UPTIME,MEMORY,"unknown")])
def test_resources_reject_missing_or_invalid_metrics(up,mem,fs):
    with pytest.raises(ValueError):aix.parse_resources(up,mem,fs)

def test_collectors_bounded_native_commands_and_partial_fixes(monkeypatch):
    output={"accounts":ACCOUNTS,"filesets":FILESETS,"oslevel":"7200-05-08-2420","uptime":UPTIME,"memory":MEMORY,"filesystem":FS}
    def capture(client,command,**kwargs):
        assert kwargs=={"timeout":60,"max_bytes":4*1024*1024}
        key=next(k for k,v in aix.COMMANDS.items() if v==command)
        return CommandResult(output.get(key,"").encode(),"denied" if key=="fixes" else "",1 if key=="fixes" else 0)
    monkeypatch.setattr(aix,"capture",capture)
    assert len(aix.accounts(Mock(),{"action":"list"})["accounts"])==2
    result=aix.patches(Mock(),{"action":"list"})
    assert result["status"]=="partial" and "denied" in result["warnings"] and len(result["packages"])==2
    assert aix.resources(Mock())["memory_mb"]["total"]==8192

@pytest.mark.parametrize("kind,action",[("accounts","create"),("accounts","delete"),("patches","plan"),("patches","apply")])
def test_aix_mixed_change_job_rejected_before_any_side_effect(kind,action):
    service=ManagementService.__new__(ManagementService);service.history_errors=[]
    service.inventory=lambda:[{"hostname":"aix","os":"AIX 7.2"},{"hostname":"linux","os":"Ubuntu"}]
    with pytest.raises(ValueError,match="read-only"):service.submit(kind,["aix","linux"],{"action":action})
    with pytest.raises(ValueError,match="read-only"):(aix.accounts if kind=="accounts" else aix.patches)(Mock(),{"action":action})


@pytest.mark.parametrize("kind,adapter",[("accounts","accounts"),("patches","patches"),("monitoring","resources")])
def test_server_routes_aix_queries_to_native_adapter_and_closes_ssh(kind,adapter,monkeypatch):
    import threading
    from common.config import load_config
    import server.service as module
    service=ManagementService.__new__(ManagementService)
    service.config=load_config(Path(__file__).resolve().parents[1]/"config/app.json")
    service.lock=threading.RLock();service.profiles={}
    row={"hostname":"aix","ip":"127.0.0.1","os":"AIX 7.2","profile":"default"}
    service.client_credentials=lambda name:(row,{},None)
    ssh=Mock();monkeypatch.setattr(module,"SSHClient",lambda *a,**k:ssh)
    collect=Mock(return_value={"native_aix":True})
    monkeypatch.setattr(aix,adapter,collect)
    result=service._target_unlocked({"kind":kind,"options":{"action":"list"}},row)
    assert result["status"]=="completed" and result["result"]["native_aix"]
    assert collect.call_args.args[0] is ssh
    ssh.close.assert_called_once()

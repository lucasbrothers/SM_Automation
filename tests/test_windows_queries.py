import json
import pytest
from monitoring.windows_queries import query_script,parse_query
from server.auth import authorize
from server.main import readable_job
from server.service import ManagementService

@pytest.mark.parametrize("kind",["accounts","patches"])
def test_read_only(kind):
    assert len(query_script(kind,{"action":"list"}))<8000
    for action in ["create","modify","delete","plan","apply"]:
        with pytest.raises(ValueError,match="read-only"):query_script(kind,{"action":action})
    authorize("operator","job.start",{"kind":kind,"options":{"action":"list"}})
    assert readable_job({"kind":kind,"options":{"action":"list"}})
    assert not readable_job({"kind":kind,"options":{"action":"apply"}})

@pytest.mark.parametrize("kind,key",[("accounts","accounts"),("patches","packages")])
def test_parser(kind,key):
    result=parse_query(kind,{"stdout":json.dumps({key:[],"warnings":[]})})
    assert result[key]==[] and result["action"]=="list"
    with pytest.raises(ValueError):parse_query(kind,{"stdout":json.dumps({key:{}})})
    with pytest.raises(ValueError):parse_query(kind,{"exit_code":1,"stderr":"denied"})

@pytest.mark.parametrize("kind,action",[("accounts","create"),("accounts","delete"),("patches","plan"),("patches","apply")])
@pytest.mark.parametrize("mixed",[False,True])
def test_submit_blocks_windows_changes(kind,action,mixed):
    service=ManagementService.__new__(ManagementService)
    rows=[{"hostname":"win","os":"Windows 11"}]
    if mixed:rows.append({"hostname":"linux","os":"Ubuntu"})
    service.history_errors=[]
    service.inventory=lambda:rows
    with pytest.raises(ValueError,match="read-only"):
        service.submit(kind,[r["hostname"] for r in rows],{"action":action})

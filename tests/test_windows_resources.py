import json
from unittest.mock import Mock
import pytest
from monitoring.windows_queries import query_script,parse_query
from server.agents import AgentManager

SAMPLE={"cpu_percent":12.5,"total_kib":8388608,"free_kib":2097152,"disk_size":100000,"disk_free":60000,"system_drive":"D:","uptime_seconds":90061}

def test_resource_units_ranges_system_drive_and_uptime():
    row=parse_query("monitoring",{"stdout":json.dumps(SAMPLE)})
    assert row["cpu_percent"]==12.5 and row["load_average"]==[]
    assert row["memory_mb"]=={"total":8192,"used":6144,"free":2048}
    assert row["root_filesystem"]["filesystem"]=="D:" and row["root_filesystem"]["capacity"]=="40%"
    assert row["uptime"]=="25시간 01분 01초"
    assert "Get-CimInstance" in query_script("monitoring",{})

@pytest.mark.parametrize("key,value",[("cpu_percent",101),("cpu_percent",True),("cpu_percent",float("nan")),("total_kib",0),("free_kib",999999999),("disk_size",0),("disk_free",100001),("uptime_seconds",-1),("system_drive","")])
def test_resources_reject_missing_or_invalid_counters(key,value):
    with pytest.raises(ValueError):parse_query("monitoring",{"stdout":json.dumps({**SAMPLE,key:value})})

def test_resources_missing_fields_rejected():
    with pytest.raises(ValueError):parse_query("monitoring",{"stdout":"{}"})

def test_agent_uses_fixed_resource_command_without_client_update():
    manager=AgentManager.__new__(AgentManager)
    def execute(job,row):
        if job["kind"]=="command":
            assert job["options"]=={"command":query_script("monitoring",{})}
            return {"status":"completed","result":{"stdout":json.dumps(SAMPLE),"exit_code":0}}
        return AgentManager.execute(manager,job,row)
    manager.execute=Mock(side_effect=execute)
    result=manager.execute({"kind":"monitoring","options":{}},{"hostname":"win"})
    assert result["status"]=="completed" and result["result"]["cpu_percent"]==12.5

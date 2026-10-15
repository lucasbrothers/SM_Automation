"""Read-only resource query against the explicitly approved local Windows PC."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from common.config import load_config
from storage.encrypted import read_secret
from desktop.client import ConnectionSettings,ServerClient
c=load_config("/opt/SM_Automation/config/app.local.json")
client=ServerClient(ConnectionSettings("127.0.0.1",c.listen_port,"/root/.config/sm-automation/ca.crt",read_secret(c.token_file).decode()))
requested=sys.argv[1]
matching=[r for r in client.call("inventory.list") if r["hostname"].casefold()==requested.casefold() or r["hostname"].casefold().startswith(requested.casefold()+"-agent-")]
assert len(matching)==1 and matching[0].get("transport")=="agent","Select a unique registered agent for the approved local PC"
job=client.call("job.start",kind="monitoring",hosts=[matching[0]["hostname"]],options={})
for _ in range(300):
 state=client.call("job.get",id=job["id"])
 if state["status"] not in {"queued","running"}:break
 time.sleep(1)
rows=client.results(job["id"])
assert state["status"]=="completed",[(r.get("status"),r.get("error")) for r in rows]
r=rows[0]["result"];assert 0<=r["cpu_percent"]<=100
assert r["memory_mb"]["total"]>0 and 0<=r["memory_mb"]["used"]<=r["memory_mb"]["total"]
assert r["root_filesystem"]["filesystem"][1]==":" and r["uptime_seconds"]>0
assert r["load_average"]==[]
print("PASS actual Windows agent resource query: CPU, physical memory, system drive, uptime and persisted job result",flush=True)

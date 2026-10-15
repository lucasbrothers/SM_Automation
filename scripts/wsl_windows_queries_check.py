"""Read-only acceptance against the explicitly approved local Windows PC."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from common.config import load_config
from storage.encrypted import read_secret
from desktop.client import ConnectionSettings,ServerClient
c=load_config("/opt/SM_Automation/config/app.local.json")
client=ServerClient(ConnectionSettings("127.0.0.1",c.listen_port,"/root/.config/sm-automation/ca.crt",read_secret(c.token_file).decode()))
host=sys.argv[1]
for kind,key in [("accounts","accounts"),("patches","packages")]:
 job=client.call("job.start",kind=kind,hosts=[host],options={"action":"list"})
 for _ in range(300):
  state=client.call("job.get",id=job["id"])
  if state["status"] not in {"queued","running"}:break
  time.sleep(1)
 rows=client.results(job["id"])
 assert state["status"]=="completed",[(r.get("status"),r.get("error"),r.get("result",{}).get("warnings")) for r in rows]
 items=rows[0]["result"][key]
 assert isinstance(items,list)
 if kind=="accounts":assert items and all(a["uid"].startswith("S-") and isinstance(a["enabled"],bool) for a in items)
 print(kind,"PASS",len(items),"rows",flush=True)
 for action in (["create","delete"] if kind=="accounts" else ["plan","apply"]):
  try:client.call("job.start",kind=kind,hosts=[host],options={"action":action})
  except Exception as e:assert "read-only" in str(e)
  else:raise AssertionError("Windows mutation was accepted")
 print(kind,"mutation rejection PASS",flush=True)

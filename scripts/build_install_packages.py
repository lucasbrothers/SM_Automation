"""Build role-specific source installers using explicit public-file allowlists."""
from pathlib import Path
import hashlib
import zipfile
root=Path(__file__).resolve().parents[1]
out=root/"release";out.mkdir(exist_ok=True)
source=[p for p in (root/"src").rglob("*.py") if "__pycache__" not in p.parts]
roles={
 "server-install": source+[root/"requirements-runtime.txt",root/"config/app.json",root/"config/ssh-profiles.example.json",root/"deploy/install-server.sh",root/"deploy/sm-automation.service"]+[root/"scripts"/name for name in ("run_server.py","provision_server.py","create_gui_account.py","import_inventory.py")],
 "gui-install": [p for p in source if p.relative_to(root/"src").parts[0] in {"desktop","shared"}]+[root/"requirements-gui.txt",root/"deploy/install-gui.ps1",root/"deploy/start-gui.cmd",root/"scripts/run_desktop.py",root/"scripts/start_desktop.ps1"],
 "client-prerequisites": []}
manifest=[]
for role, files in roles.items():
 files += [root/"docs/production-test.md",root/"docs/offline-deployment.md",root/"docs/ci-dashboard.md"]
 path=out/(role+".zip")
 with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
  for file in sorted(set(files)):
   content=file.read_bytes()
   if file.suffix == ".sh": content=content.replace(b"\r\n",b"\n")
   archive.writestr(file.relative_to(root).as_posix(),content)
 manifest.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+path.name)
 print(role+": "+str(len(set(files)))+" public files")
(out/"SHA256SUMS.txt").write_text("\n".join(manifest)+"\n",encoding="ascii")

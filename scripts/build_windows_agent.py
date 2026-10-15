"""Build standalone Windows CLIENT binaries using the installed .NET Framework compiler."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from ci.collector import WINDOWS_SCRIPT
out=root/'release';out.mkdir(exist_ok=True)
compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if not compiler.exists():raise SystemExit('Build requires Windows .NET Framework 4.x compiler')
ci=out/'agent-ci.ps1';ci.write_text(WINDOWS_SCRIPT,encoding='utf-8')
common=[str(compiler),'/nologo','/utf8output','/optimize+','/platform:anycpu','/r:System.dll','/r:System.Core.dll','/r:System.Web.Extensions.dll','/r:System.Security.dll','/r:System.ServiceProcess.dll']
subprocess.run(common+['/target:exe','/out:'+str(out/'SM.Agent.exe'),'/resource:'+str(ci)+',ci-script',str(root/'windows-client/Agent.cs')],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
subprocess.run(common+['/target:winexe','/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/win32manifest:'+str(root/'windows-client/installer.manifest'),'/out:'+str(out/'windows-client-base.exe'),'/resource:'+str(out/'SM.Agent.exe')+',agent-exe',str(root/'windows-client/Installer.cs')],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
subprocess.run([str(out/'SM.Agent.exe'),'--self-test'],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
print('Windows CLIENT installer built; no Python installation needed on CLIENT')

# Non-elevated rendering build: never installs a service or changes system settings.
preview_manifest=out/'agent-preview.manifest'
preview_manifest.write_text((root/'windows-client/installer.manifest').read_text(encoding='utf-8-sig').replace('requireAdministrator','asInvoker'),encoding='utf-8')
subprocess.run(common+['/target:winexe','/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/win32manifest:'+str(preview_manifest),'/out:'+str(out/'windows-client-preview.exe'),'/resource:'+str(out/'SM.Agent.exe')+',agent-exe',str(root/'windows-client/Installer.cs')],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
(root/'logs').mkdir(exist_ok=True)
subprocess.run([str(out/'windows-client-preview.exe'),'--render-preview',str(root/'logs/windows-client-installer-preview.png')],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

"""Administrator-only, read-only ISO mounts and bounded package browsing."""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time

ROOT = Path('/srv/sm-automation/media')
LOCK = threading.Lock()


def handle(method, params):
    with LOCK:
        return dispatch(method, params)


def dispatch(method, params):
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if ROOT.is_symlink():
        raise ValueError('Media root cannot be a link')
    if method == 'media.mount':
        path = params.get('path', '')
        if not isinstance(path, str) or not path.startswith('/') or not path.lower().endswith('.iso') or '\x00' in path:
            raise ValueError('Select an absolute SERVER ISO path')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('ISO must be a regular file')
            identity = hashlib.sha256(f'{path}:{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}'.encode()).hexdigest()[:32]
            target = ROOT / identity
            target.mkdir(mode=0o700, exist_ok=True)
            if target.is_symlink(): raise ValueError('Mount point cannot be a link')
            if not os.path.ismount(target):
                subprocess.run(['mount','-o','loop,ro,nodev,nosuid,noexec',f'/proc/self/fd/{fd}',str(target)],pass_fds=(fd,),check=True,capture_output=True,timeout=30)
            return {'id':identity,'path':str(target),'read_only':True}
        finally:
            os.close(fd)
    identity = params.get('id','')
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):
        raise ValueError('Invalid ISO mount ID')
    target = ROOT / identity
    if target.is_symlink() or not os.path.ismount(target):
        raise ValueError('ISO is not mounted')
    if method == 'media.unmount':
        subprocess.run(['umount',str(target)],check=True,capture_output=True,timeout=30)
        target.rmdir()
        return {'unmounted':True}
    if method != 'media.packages': raise ValueError('Unknown media method')
    query = params.get('query','')
    if not isinstance(query,str) or len(query)>200: raise ValueError('Search text too long')
    entries=[]; scanned=0; truncated=False; deadline=time.monotonic()+10
    for directory, folders, files in os.walk(target,followlinks=False):
        scanned+=1
        if scanned>100000 or time.monotonic()>deadline: truncated=True; break
        folders.sort()
        for name in sorted(files):
            scanned+=1
            if scanned>100000 or time.monotonic()>deadline: truncated=True; break
            if Path(name).suffix.lower() in {'.deb','.rpm','.msu','.cab','.msi','.exe','.wim','.esd'} and query.casefold() in name.casefold():
                path=Path(directory)/name
                if path.is_symlink(): continue
                entries.append({'name':name,'path':str(path),'size':path.stat().st_size,'install_supported':Path(name).suffix in {'.deb','.rpm'}})
                if len(entries)>=1000: truncated=True; break
        if truncated:break
    return {'entries':entries,'truncated':truncated,'note':'Ubuntu live ISO may contain only a few DEBs. Windows WIM/ESD is an OS image, not an installable Linux patch. Windows patch changes remain unsupported.'}

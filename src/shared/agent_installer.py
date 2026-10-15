"""Public bootstrap descriptor appended to a server-bound Windows installer."""
from pathlib import Path
import hashlib
import json


def bind_installer(source,target,fingerprint):
    if len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint):raise ValueError('Invalid SERVER identity')
    if Path(source).resolve()==Path(target).resolve():raise ValueError('Save a separate installer copy')
    content=Path(source).read_bytes()
    if not content.startswith(b'MZ'):raise ValueError('Invalid Windows installer')
    marker=b'\nSM_AUTOMATION_SERVER_PIN_V1\n'
    if marker in content[-4096:]:raise ValueError('Choose the original base installer')
    content+=marker+json.dumps({'sha256':fingerprint},separators=(',',':')).encode()
    Path(target).write_bytes(content)
    Path(str(target)+'.sha256').write_text(hashlib.sha256(content).hexdigest()+'  '+Path(target).name+'\n',encoding='utf-8')
    return str(target)

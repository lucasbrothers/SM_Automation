"""Compare backed-up configuration files without extracting archives or changing CLIENTs."""
import base64
import difflib
import hashlib
import io
import json
import posixpath
import re
import tarfile
from backup.profiles import LINUX_PATHS,AIX_PATHS,unix_archive,windows_files
from engine.remote import capture,privileged
from monitoring.connections import os_family


def record(content,metadata):
    text=None
    if len(content)<=65536 and b'\x00' not in content:
        try:text=content.decode('utf-8')
        except UnicodeError:pass
    return {'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'metadata':metadata,'text':text}


def unpack(content,windows=False):
    records={}
    if windows:
        data=json.loads(content.decode('utf-8-sig'))
        if data.get('format')!='base64-files-v1' or data.get('errors'):raise ValueError('Incomplete Windows configuration capture')
        for entry in data['files']:
            path=entry['path'].replace('\\','/').casefold()
            if path in records:raise ValueError('Duplicate configuration path')
            records[path]=record(base64.b64decode(entry['content'],validate=True),{})
        return records
    total=0
    with tarfile.open(fileobj=io.BytesIO(content),mode='r:*') as archive:
        for index,member in enumerate(archive):
            if index>=10000 or total+member.size>96*1024*1024:raise ValueError('Configuration archive exceeds comparison bounds')
            if '..' in member.name.split('/'):raise ValueError('Unsafe configuration path')
            path=posixpath.normpath('/'+member.name.lstrip('/'))
            metadata={'type':member.type.decode('ascii',errors='replace'),'mode':oct(member.mode),'uid':member.uid,'gid':member.gid,'link':member.linkname}
            content=b''
            if member.isfile():
                stream=archive.extractfile(member)
                if stream is None:raise ValueError('Unreadable configuration member')
                content=stream.read(member.size+1);total+=len(content)
                if len(content)!=member.size:raise ValueError('Incomplete configuration member')
            entry=record(content,metadata)
            if path in records and records[path]!=entry:raise ValueError('Conflicting duplicate configuration path')
            records[path]=entry
    return records


def safe_text(path,text):
    if text is None:return None
    if re.search(r'PRIVATE KEY',text) or re.search(r'(?i)(?:\.key$|/shadow$|/gshadow$|/[^/]*token[^/]*$)',path):return '[민감 파일: 내용 미표시]\n'
    return '\n'.join('[민감값 포함 행 생략]' if re.search(r'(?i)(password|passwd|secret|token|bindpw|credential|authorization)\s*[:=\s]',line) else line for line in text.splitlines())+'\n'


def compare(old,new):
    rows=[];budget=1024*1024
    for path in sorted(set(old)|set(new)):
        before=old.get(path);after=new.get(path)
        state='added' if before is None else 'removed' if after is None else 'unchanged' if (before['sha256'],before['metadata'])==(after['sha256'],after['metadata']) else 'changed'
        detail=''
        if state!='unchanged':
            left=safe_text(path,before['text']) if before else ''
            right=safe_text(path,after['text']) if after else ''
            if left is not None and right is not None:
                detail=''.join(difflib.unified_diff(left.splitlines(True),right.splitlines(True),fromfile='백업/'+path,tofile='현재/'+path))
                if len(detail)>16000:detail=detail[:16000]+'\n[차이 표시 생략: 길이 제한]\n'
            else:detail='바이너리 또는 큰 파일: 크기·SHA256으로 변경 판정'
            if before and after and before['metadata']!=after['metadata']:detail+='\n메타데이터: '+json.dumps(before['metadata'],ensure_ascii=False)+' → '+json.dumps(after['metadata'],ensure_ascii=False)
            if not detail:detail='내용의 SHA256이 변경됨 (민감값은 표시하지 않음)'
        if len(detail)>budget:detail='상세 차이 표시 한도 초과: SHA256 및 변경 상태 확인'
        else:budget-=len(detail)
        rows.append({'path':path,'status':state,'before_size':before['size'] if before else None,'after_size':after['size'] if after else None,'before_sha256':before['sha256'] if before else '', 'after_sha256':after['sha256'] if after else '', 'diff':detail})
    return rows


def current_compare(client,server,config,store,artifact,run_id,progress=None):
    if artifact.get('status')!='completed':raise ValueError('Baseline configuration capture is incomplete; select a complete configuration artifact')
    path=artifact['path']
    if store.path(path).stat().st_size>128*1024*1024:raise ValueError('Baseline exceeds comparison bounds')
    old_content=store.read_bytes(path);family=os_family(server.os)
    command=windows_files() if family=='windows' else privileged(unix_archive(AIX_PATHS if family=='aix' else LINUX_PATHS),config.privilege)
    if progress:progress(server.hostname+': reading current configuration for comparison')
    current=capture(client,command,timeout=config.backup_timeout,max_bytes=config.max_capture_mb*1024*1024)
    unexpected=[line for line in current.stderr.splitlines() if line.strip() and not line.startswith('Missing optional path: ')]
    if current.exit_code or unexpected:raise ValueError('Current configuration capture incomplete; comparison refused')
    rows=compare(unpack(old_content,family=='windows'),unpack(current.stdout,family=='windows'))
    changes=[row for row in rows if row['status']!='unchanged']
    result={'status':'completed','files':rows,'changed':len(changes),'total':len(rows),'baseline_path':path,'warnings':current.stderr,'scope':'Configuration files only; command snapshots and timestamps excluded'}
    report_path='comparisons/'+run_id+'/'+server.hostname+'.json.enc'
    store.write_json(report_path,result)
    return {key:value for key,value in result.items() if key!='files'} | {'files':[], 'report_path':report_path}

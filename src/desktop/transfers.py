"""Recursive, resumable transfers; only verified complete files are published."""
import base64
import hashlib
import json
import os
import posixpath
import uuid
from pathlib import Path

CHUNK=1024*1024


def digest(path, length=None):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while length is None or length:
            block=stream.read(CHUNK if length is None else min(CHUNK,length))
            if not block:
                if length: raise ValueError('Local source changed')
                break
            value.update(block)
            if length is not None:length-=len(block)
    return value.hexdigest()


def safe_name(name):
    if not isinstance(name,str) or not name or name in {'.','..'} or any(c in name for c in '/\\\x00:'):
        raise ValueError('Unsupported file name: '+str(name))
    return name


class Interrupted(Exception): pass


class Transfers:
    def __init__(self,client,state_path):
        self.client=client;self.path=Path(state_path)
        self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'records':{}}

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=self.path.with_name(self.path.name+'.new')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(self.state,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(0o600);os.replace(temporary,self.path)

    def check(self,stop):
        if stop():raise Interrupted(stop())

    def run(self,payload,local_dir,remote_dir,progress,stop,resume=False):
        if resume:
            job=self.state.get('job')
            if not job:return 'No paused transfer to resume.'
            payload=job['payload'];local_dir=job['local'];remote_dir=job['remote']
        elif self.state.get('job'):
            raise ValueError('Resume or discard the paused transfer before starting another.')
        else:
            self.state['job']={'payload':payload,'local':local_dir,'remote':remote_dir};self.save()
        messages=[]
        try:
            for entry in payload['files']:
                self.walk(payload['side'],entry['path'],local_dir,remote_dir,progress,stop,messages,0)
            if self.state['records']:
                raise ValueError('Interrupted source files are missing; discard the paused transfer')
        except Interrupted as exc:
            if str(exc)=='cancel':
                self.discard();return 'Transfer cancelled; pending files removed.'
            return 'Transfer paused. Use Resume, including after restarting the GUI.'
        except Exception as exc:
            return 'Transfer incomplete: '+str(exc)+' — use Resume or Discard paused transfer.'
        self.state.pop('job',None);self.save()
        return '\n'.join(messages) or 'No files selected.'

    def walk(self,side,source,local_dir,remote_dir,progress,stop,messages,depth):
        self.check(stop)
        if depth>128:raise ValueError('Folder nesting exceeds 128 levels')
        name=safe_name(Path(source).name if side=='local' else posixpath.basename(source.rstrip('/')))
        if side=='local':
            path=Path(source)
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Symbolic links/junctions are not transferred: '+source)
            if path.is_dir():
                destination=posixpath.join(remote_dir,name);self.client.call('file.mkdir',path=destination)
                for child in sorted(path.iterdir()):self.walk(side,str(child),local_dir,destination,progress,stop,messages,depth+1)
                return
            if not path.is_file():raise ValueError('Select a regular file or folder')
            target=posixpath.join(remote_dir,name)
        else:
            # Listing the parent identifies real folders without following directory links.
            parent=posixpath.dirname(source.rstrip('/')) or '/'
            entries=self.client.call('file.list',path=parent)['entries']
            entry=next((e for e in entries if e['name']==name),None)
            if not entry:raise ValueError('Source no longer exists: '+source)
            if entry['directory']:
                destination=Path(local_dir)/name
                if destination.is_symlink() or getattr(destination,'is_junction',lambda:False)():raise ValueError('Destination cannot be a link')
                destination.mkdir(exist_ok=True)
                for child in self.client.call('file.list',path=source)['entries']:
                    safe_name(child['name'])
                    self.walk(side,posixpath.join(source,child['name']),str(destination),remote_dir,progress,stop,messages,depth+1)
                return
            if not entry['regular']:raise ValueError('Symbolic links and special files are not transferred')
            target=str(Path(local_dir)/name)
        self.file(side,source,target,progress,stop)
        messages.append(name+': Success — '+target)

    def file(self,side,source,target,progress,stop):
        identity=hashlib.sha256(json.dumps([side,source,target]).encode()).hexdigest()
        records=self.state['records'];record=records.get(identity)
        signature={'size':Path(source).stat().st_size,'sha256':digest(source)} if side=='local' else self.client.call('file.stat',path=source)
        if record and record['signature']!=signature:raise ValueError('Original file changed; discard the paused transfer first')
        if side=='local':
            try:existing=self.client.call('file.stat',path=target)
            except RuntimeError:existing=None
        else:
            destination=Path(target)
            if destination.is_symlink():raise ValueError('Destination cannot be a link')
            existing={'size':destination.stat().st_size,'sha256':digest(destination)} if destination.exists() else None
        if existing:
            if existing['size']==signature['size'] and existing['sha256']==signature['sha256']:
                if record:self.remove_record(identity)
                return
            raise FileExistsError('Different destination file already exists: '+target)
        if not record:
            pending=posixpath.join(posixpath.dirname(target),'.sm-upload-'+uuid.uuid4().hex) if side=='local' else str(Path(target).parent/('.sm-download-'+uuid.uuid4().hex))
            record={'side':side,'pending':pending,'signature':signature,'offset':0};records[identity]=record;self.save()
        pending=record['pending'];offset=record['offset']
        continuing=False
        if side=='local':
            actual=self.client.call('file.pending',path=pending)
            continuing=actual['exists'];offset=actual['size']
            if continuing and (offset>signature['size'] or actual['sha256']!=digest(source,offset)):
                raise ValueError('Partial upload differs from source')
        elif Path(pending).exists():
            offset=Path(pending).stat().st_size
            if offset>signature['size']:raise ValueError('Partial download exceeds source')
            actual=self.client.call('file.stat',path=source,length=offset)
            if actual['sha256']!=digest(pending):raise ValueError('Partial download differs from source')
        if side=='local':
            with open(source,'rb') as stream:
                stream.seek(offset)
                while offset<signature['size'] or signature['size']==0 and offset==0 and not continuing:
                    self.check(stop);block=stream.read(CHUNK)
                    if not block and offset<signature['size']:raise ValueError('Source changed')
                    self.client.call('file.upload',path=pending,offset=offset,content=base64.b64encode(block).decode(),final=offset+len(block)>=signature['size'],**{'continue':continuing})
                    offset+=len(block);record['offset']=offset;self.save();progress(f'Upload {source}: {offset:,} / {signature["size"]:,} bytes')
                    if offset>=signature['size']:break
            self.check(stop)
            actual=self.client.call('file.stat',path=pending)
            if actual['sha256']!=signature['sha256']:raise ValueError('Upload content verification failed')
            self.client.call('file.commit',path=pending,target=target,size=signature['size'])
        else:
            with open(pending,'ab' if Path(pending).exists() else 'xb') as stream:
                while offset<signature['size']:
                    self.check(stop);result=self.client.call('file.download',path=source,offset=offset)
                    block=base64.b64decode(result['content'],validate=True)
                    if not block or result['size']!=signature['size']:raise ValueError('Source changed')
                    stream.write(block);stream.flush();os.fsync(stream.fileno());offset+=len(block)
                    record['offset']=offset;self.save();progress(f'Download {source}: {offset:,} / {signature["size"]:,} bytes')
            self.check(stop)
            if digest(pending)!=signature['sha256']:raise ValueError('Download content verification failed')
            os.link(pending,target);Path(pending).unlink()
        records.pop(identity,None);self.save()

    def remove_record(self,identity):
        record=self.state['records'][identity]
        if record['side']=='local':self.client.call('file.abort',path=record['pending'])
        else:Path(record['pending']).unlink(missing_ok=True)
        del self.state['records'][identity];self.save()

    def discard(self):
        for identity in list(self.state['records']):self.remove_record(identity)
        self.state.pop('job',None);self.save()

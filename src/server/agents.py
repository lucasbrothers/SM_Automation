"""Outbound Windows agents: scoped auto-enrollment, signed polling and durable tasks."""
from __future__ import annotations
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import time
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from shared.ci_schema import AUTO_FIELDS
from ci.collector import windows_smt

PRIVATE_NETWORKS = ['127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','::1/128','fc00::/7']
SUPPORTED = {'ci_inventory','connections','command','transfer','backup_artifact','backup'}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):
        raise ValueError('Invalid device identity')
    return value


def public_key(value):
    try:
        n=base64.b64decode(value['modulus'],validate=True);e=base64.b64decode(value['exponent'],validate=True)
        if not 256<=len(n)<=512 or len(e)>4:raise ValueError()
        key=rsa.RSAPublicNumbers(int.from_bytes(e,'big'),int.from_bytes(n,'big')).public_key()
        if key.key_size<2048:raise ValueError()
        return key
    except Exception:
        raise ValueError('Invalid device public key') from None


def key_fingerprint(key):
    return hashlib.sha256(key.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


class AgentManager:
    def __init__(self,service):
        self.service=service;self.store=service.data;self.lock=service.lock
        self.bindings=self.store.read_json('agents/bindings.json.enc',{})
        self.policy=self.store.read_json('agents/enrollment.json.enc',{'enabled':False,'networks':PRIVATE_NETWORKS,'expires_at':'','max_new':1000,'used':0})
        self.cache={};self.challenges={};self.rates=defaultdict(deque);self.tasks={};self.task_ready=threading.Condition(self.lock)

    def device(self,identity):
        identifier(identity)
        if identity in self.cache:return self.cache[identity]
        record=self.store.read_json('agents/devices/'+identity+'.json.enc')
        if record is not None:
            if len(self.cache)>=8192:self.cache.pop(next(iter(self.cache)))
            self.cache[identity]=record
        return record

    def save(self,identity,value):
        self.store.write_json('agents/devices/'+identity+'.json.enc',value);self.cache[identity]=value

    def decorate(self,rows):
        values=[]
        for row in rows:
            identity=self.bindings.get(row['hostname'])
            if identity:
                record=self.device(identity)
                if record:
                    row={**row,'transport':'agent','agent_id':identity,'agent_status':self.state(record),'last_seen':record.get('last_seen','')}
            values.append(row)
        return values

    def state(self,row):
        if row.get('removed'):return 'removed'
        if row.get('revoked'):return 'revoked'
        if row.get('uninstalled'):return 'uninstalled'
        last=datetime.fromisoformat(row['last_seen']).timestamp() if row.get('last_seen') else 0
        return 'online' if time.time()-last<120 else 'offline'

    def configure(self,params):
        networks=params.get('networks',PRIVATE_NETWORKS);hours=params.get('hours',24);limit=params.get('max_new',1000)
        if not isinstance(networks,list) or not 1<=len(networks)<=64:raise ValueError('Enter allowed enrollment networks')
        networks=[str(ipaddress.ip_network(n,strict=False)) for n in networks]
        if type(hours) is not int or not 1<=hours<=168 or type(limit) is not int or not 1<=limit<=5000:raise ValueError('Invalid enrollment limits')
        policy={'enabled':bool(params.get('enabled',True)),'networks':networks,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat(),'max_new':limit,'used':0}
        self.store.write_json('agents/enrollment.json.enc',policy);self.policy=policy
        return dict(policy)

    def may_enroll(self,peer):
        policy=self.policy
        return bool(policy.get('enabled') and policy.get('expires_at') and datetime.fromisoformat(policy['expires_at']).timestamp()>time.time() and policy.get('used',0)<policy['max_new'] and any(ipaddress.ip_address(peer) in ipaddress.ip_network(n) for n in policy['networks']))

    def hello(self,params,peer):
        identity=identifier(params.get('device_id'));key=public_key(params.get('public_key',{}));fingerprint=key_fingerprint(key)
        record=self.device(identity)
        if not record and identity in self.bindings.values():raise ValueError('Device identity registry requires recovery')
        if record and (record.get('revoked') or record.get('uninstalled') or record['fingerprint']!=fingerprint):raise ValueError('Device authentication denied')
        if not record and not self.may_enroll(peer):raise ValueError('New device enrollment is closed or this network is not allowed')
        current=time.monotonic()
        self.challenges={k:v for k,v in self.challenges.items() if v['until']>current}
        if len(self.challenges)>=2048:raise ValueError('Enrollment busy; retry later')
        # Bound distinct source tracking as well as challenge allocation.
        rate_key=peer+":"+identity if record else peer
        if rate_key not in self.rates and len(self.rates)>=8192:self.rates.pop(next(iter(self.rates)))
        hits=self.rates[rate_key]
        while hits and hits[0]<current-60:hits.popleft()
        if len(hits)>=(10 if record else 120):raise ValueError('Device request rate exceeded; retry later')
        hits.append(current)
        challenge=uuid.uuid4().hex;nonce=base64.b64encode(secrets.token_bytes(32)).decode()
        self.challenges[challenge]={'device_id':identity,'key':key,'fingerprint':fingerprint,'public_key':params['public_key'],'nonce':nonce,'until':current+90,'peer':peer}
        return {'challenge_id':challenge,'nonce':nonce}

    def exchange(self,params,peer):
        challenge=self.challenges.pop(params.get('challenge_id'),None)
        if not challenge or challenge['until']<time.monotonic() or challenge['peer']!=peer:raise ValueError('Expired device challenge')
        payload=params.get('payload')
        if not isinstance(payload,str) or len(payload.encode('utf-8'))>13*1024*1024:raise ValueError('Invalid device payload')
        message=('SM-AUTOMATION-AGENT-v1\n'+params['challenge_id']+'\n'+challenge['nonce']+'\n'+payload).encode()
        try:challenge['key'].verify(base64.b64decode(params['signature'],validate=True),message,padding.PKCS1v15(),hashes.SHA256())
        except Exception:raise ValueError('Device signature is invalid') from None
        data=json.loads(payload)
        if not isinstance(data,dict) or data.get('device_id')!=challenge['device_id']:raise ValueError('Invalid signed device identity')
        identity=challenge['device_id'];record=self.device(identity)
        if record and (record.get('revoked') or record.get('uninstalled') or record['fingerprint']!=challenge['fingerprint']):raise ValueError('Device is revoked')
        observation=data.get('observation')
        if observation is not None and (not isinstance(observation,dict) or len(json.dumps(observation).encode())>256*1024):raise ValueError('Invalid CI observation')
        if not record:
            if not self.may_enroll(peer):raise ValueError('New device enrollment is closed')
            record=self.register(identity,challenge,data,peer)
        if record.get('registration_pending'):record=self.finish_registration(record)
        inventory=self.store.read_json('inventory.json.enc',[])
        host=next((r for r in inventory if r['hostname']==record['hostname']),None)
        if host is None:raise ValueError('Device was removed from inventory; revoke/re-enroll explicitly')
        record={**record,'last_seen':timestamp(),'peer_ip':peer,'uninstalled':bool(data.get('uninstall',False)),'version':str(data.get('version',record.get('version','')))[:80]}
        observation=data.get('observation')
        if observation is not None:
            if not isinstance(observation,dict) or len(json.dumps(observation).encode())>256*1024:raise ValueError('Invalid CI observation')
            observation={**observation,**windows_smt(observation.get('cpu_topology'))}
            observation={k:observation.get(k) for k in AUTO_FIELDS}
            if any(v is not None and not isinstance(v,(str,int,float,bool)) for v in observation.values()):raise ValueError('Invalid CI observation fields')
            address=self.address(observation.get('primary_ip'),peer)
            if host['ip']!=address:
                host['ip']=address;self.store.write_json('inventory.json.enc',inventory)
            self.service.ci_registry().observe(host,observation)
        elif data.get('collection_error'):
            self.service.ci_registry().observe(host,error='Windows agent CI collection failed; check agent logs')
        ack=[]
        results=data.get('results',[])
        if not isinstance(results,list) or len(results)>1:raise ValueError('Return one device task result at a time')
        tasks=self.read_tasks(identity)
        changed=False;backup_ack=False
        for result in results:
            if not isinstance(result,dict):raise ValueError('Invalid task result')
            task=next((t for t in tasks if t['id']==result.get('id')),None)
            if task is None:continue
            if task['state'] not in {'completed','expired','cancelled'}:
                if task['state']!='issued':raise ValueError('Task was not issued')
                if result.get('status') not in {'completed','failed'}:raise ValueError('Invalid task status')
                limit=12*1024*1024 if task['kind'] in {'transfer','backup_artifact'} else 2*1024*1024
                if len(json.dumps(result,ensure_ascii=False).encode())>limit:raise ValueError('Agent task result exceeds its limit')
                if not isinstance(result.get('result',{}),dict):raise ValueError('Invalid agent result body')
                result={**result,'error':str(result.get('error',''))[:1500]}
                self.store.write_json('agents/results/'+task['id']+'.json.enc',result)
                task.update(state='completed');changed=True
            ack.append(result['id'])
            backup_ack=backup_ack or task['kind']=='backup_artifact'
        if backup_ack and changed:
            self.save_tasks(identity,tasks);changed=False;self.save(identity,record)
            # Release the registry lock while the backup writer prepares its next artifact.
            # This avoids a full 30-second idle poll between every read-only backup step.
            self.task_ready.wait_for(lambda:any(t['state']=='pending' for t in self.read_tasks(identity)),timeout=.75)
            record=self.device(identity)
            if not record or record.get('revoked'):raise ValueError('Device is revoked')
            tasks=self.read_tasks(identity)
        offered=None
        if not record['uninstalled']:
            for task in tasks:
                if task['state'] in {'pending','issued'}:
                    job=self.service.jobs.get(task['job_id'],{})
                    if job.get('cancel_requested') or job.get('status') not in {'queued','running'}:
                        task['state']='cancelled';changed=True;continue
                    if time.time()>task['expires']:
                        task['state']='expired';changed=True;continue
                    if time.time()<task.get('not_before',0):continue
                    task['state']='issued';changed=True;offered={k:task[k] for k in ('id','kind','options')}
                    if task['kind']=='transfer' and task['options']['direction']=='download':
                        from server.files import LIMIT
                        import stat
                        fd=os.open(task['options']['server_path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                        with os.fdopen(fd,'rb') as source:
                            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):raise ValueError('Select a regular SERVER file')
                            content=source.read(LIMIT+1)
                        if len(content)>LIMIT:raise ValueError('CLIENT transfer limit is 8 MiB')
                        digest=hashlib.sha256(content).hexdigest()
                        if task.get('expected_sha256') and task['expected_sha256']!=digest:raise ValueError('SERVER file changed before task redelivery')
                        task['expected_sha256']=digest
                        offered['options']={**task['options'],'content':base64.b64encode(content).decode(),'sha256':digest}
                    break
        if changed:self.save_tasks(identity,tasks)
        self.save(identity,record)
        return {'hostname':record['hostname'],'ack':ack,'task':offered,'poll_seconds':30}

    def read_tasks(self,identity):
        if identity not in self.tasks:self.tasks[identity]=self.store.read_json('agents/tasks/'+identity+'.json.enc',[])
        return self.tasks[identity]

    def save_tasks(self,identity,tasks):
        self.store.write_json('agents/tasks/'+identity+'.json.enc',tasks);self.tasks[identity]=tasks

    def address(self,value,peer):
        try:
            address=ipaddress.ip_address(value)
            if not address.is_unspecified and not address.is_multicast:return str(address)
        except (ValueError,TypeError):pass
        return str(ipaddress.ip_address(peer))

    def register(self,identity,challenge,data,peer):
        inventory=self.store.read_json('inventory.json.enc',[])
        if len(inventory)>=5000:raise ValueError('Inventory capacity reached')
        name=data.get('hostname')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,252}',name):raise ValueError('Invalid Windows hostname')
        used={r['hostname'].casefold() for r in inventory}
        if name.casefold() in used:name=name[:215]+'-agent-'+identity[:16]
        if name.casefold() in used:raise ValueError('Duplicate device hostname')
        observation=data.get('observation') or {}
        host={'hostname':name,'ip':self.address(observation.get('primary_ip'),peer),'os':'Windows','profile':'default'}
        record={'id':identity,'hostname':name,'fingerprint':challenge['fingerprint'],'public_key':challenge['public_key'],'registered_at':timestamp(),'last_seen':timestamp(),'peer_ip':peer,'revoked':False,'uninstalled':False}
        record.update(registration_pending=True,pending_host=host)
        self.save(identity,record)
        return self.finish_registration(record)

    def finish_registration(self,record):
        identity=record['id'];host=dict(record['pending_host'])
        inventory=self.store.read_json('inventory.json.enc',[])
        existing=next((r for r in inventory if r.get('agent_id')==identity or self.bindings.get(r['hostname'])==identity),None)
        if existing:
            host=existing
        else:
            if len(inventory)>=5000:raise ValueError('Inventory capacity reached')
            used={r['hostname'].casefold() for r in inventory}
            if host['hostname'].casefold() in used:host['hostname']=host['hostname'][:200]+'-agent-'+identity[:16]
            if host['hostname'].casefold() in used:raise ValueError('Duplicate device hostname during registration recovery')
            host.update(agent_id=identity,transport='agent')
            inventory.append(host);self.store.write_json('inventory.json.enc',inventory)
        self.bindings[host['hostname']]=identity
        self.store.write_json('agents/bindings.json.enc',self.bindings)
        self.policy['used']=self.policy.get('used',0)+1
        self.store.write_json('agents/enrollment.json.enc',self.policy)
        record={**record,'hostname':host['hostname'],'registration_pending':False}
        record.pop('pending_host',None);self.save(identity,record)
        return record

    def rpc(self,method,params,peer):
        with self.lock:
            if method=='agent.hello':return self.hello(params,peer)
            if method=='agent.exchange':return self.exchange(params,peer)
        raise ValueError('Unknown device request')

    def listing(self):
        rows=[]
        for path in sorted(self.store.root.glob('agents/devices/*.json.enc')):
            record=self.device(path.name.removesuffix('.json.enc'))
            if record and not record.get("removed"):rows.append({k:record.get(k,'') for k in ('id','hostname','registered_at','last_seen','peer_ip','version')}|{'status':self.state(record)})
        return rows

    def revoke(self,identity,remove=False):
        record=self.device(identity)
        if not record:raise ValueError('Unknown device')
        for task in self.read_tasks(identity):
            if task['state']=='pending':task['state']='cancelled'
        self.save_tasks(identity,self.read_tasks(identity))
        record={**record,'revoked':True,'revoked_at':timestamp()};self.save(identity,record)
        if remove:
            record['removed']=True;self.save(identity,record)
            self.bindings.pop(record['hostname'],None);self.store.write_json('agents/bindings.json.enc',self.bindings)
            rows=[r for r in self.store.read_json('inventory.json.enc',[]) if r['hostname']!=record['hostname']]
            self.store.write_json('inventory.json.enc',rows)
        return {'id':identity,'status':'revoked','removed':bool(remove)}

    def task_id(self,job,row):
        suffix=job.get('options',{}).get('script','') if job['kind']=='backup_artifact' else ''
        return hashlib.sha256((job['id']+'\0'+row['hostname']+suffix).encode()).hexdigest()[:32]

    def prepare(self,job,row,index=0,total=1):
        identity=row['agent_id'];record=self.device(identity)
        if not record or record.get('revoked') or record.get('uninstalled'):raise ValueError('Windows agent is revoked or uninstalled')
        if job['kind'] not in SUPPORTED:raise ValueError('Windows agent does not support this operation')
        if job['kind'] in {'backup','backup_artifact'} and record.get('version')!='1.1.0':raise ValueError('Windows backup requires CLIENT agent 1.1.0; run the updated installer on CLIENT to upgrade')
        if job['kind']=='command' and len(job['options'].get('command',''))>8000:raise ValueError('Windows agent command limit is 8000 characters')
        identity_task=self.task_id(job,row)
        tasks=self.read_tasks(identity)
        if any(t['id']==identity_task for t in tasks):return identity_task
        tasks=[t for t in tasks if t['state'] in {'pending','issued'} and t['expires']>time.time()]
        if len(tasks)>=4:raise ValueError('Windows agent task queue is full')
        options=dict(job['options'])
        if job['kind']=='transfer':
            from server.files import validate,LIMIT
            options=validate({k:v.replace('{hostname}',row['hostname']) if isinstance(v,str) else v for k,v in options.items()})
            if options['direction']=='download':
                import stat
                info=os.stat(options['server_path'],follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_size>LIMIT:raise ValueError('SERVER source must be a regular file up to 8 MiB')
        due=time.time()+job.get('spread_seconds',0)*index/max(1,total-1)
        task={'id':identity_task,'job_id':job['id'],'kind':job['kind'],'options':options,'state':'pending','not_before':due,'expires':due+180}
        tasks.append(task);self.save_tasks(identity,tasks)
        with self.task_ready:self.task_ready.notify_all()
        return identity_task

    def backup(self,job,row):
        with self.lock:
            if self.device(row["agent_id"]).get("version")!="1.1.0":raise ValueError("Windows backup requires CLIENT agent 1.1.0; run the updated installer to upgrade")
        from core.inventory import ServerRecord
        from backup.collector import backup_server
        from engine.remote import CommandResult
        from dataclasses import replace
        config=replace(self.service.config,max_capture_mb=min(self.service.config.max_capture_mb,4))
        runner=self.backup_runner(job,row)
        with self.service.heavy_slots:
            result=backup_server(None,ServerRecord(row['hostname'],row['ip'],row['os']),config,self.service.backups,job['id'],lambda text:self.service._progress(job,text),runner=runner,windows_file_limit_mb=2)
        return {**row,'status':result['status'],'result':result}

    def backup_runner(self,job,row):
        from engine.remote import CommandResult
        def runner(command):
            script=base64.b64decode(command.rsplit(' ',1)[1],validate=True).decode('utf-16-le')
            output=self.execute({**job,'kind':'backup_artifact','options':{'script':script}},row)
            data=output.get('result',{})
            if 'stdout' not in data:raise ValueError(output.get('error','Windows backup artifact failed'))
            return CommandResult(data['stdout'].encode('utf-8'),str(data.get('stderr','')),int(data['exit_code']))
        return runner

    def compare_backup(self,job,row):
        from core.inventory import ServerRecord
        from backup.compare import current_compare
        artifact=self.service.baseline_configuration(job,row)
        with self.service.heavy_slots:
            result=current_compare(None,ServerRecord(row['hostname'],row['ip'],row['os']),self.service.config,self.service.backups,artifact,job['id'],runner=self.backup_runner(job,row),windows_file_limit_mb=2)
        return {**row,'status':'completed','result':result}

    def execute(self,job,row):
        try:
            if job["kind"]=="backup":return self.backup(job,row)
            if job["kind"]=="backup_compare":return self.compare_backup(job,row)
            with self.lock:
                task_id=self.prepare(job,row)
            deadline=time.monotonic()+240
            while time.monotonic()<deadline and not self.service.closed:
                with self.lock:
                    current=self.device(row['agent_id'])
                    if not current or current.get('revoked'):raise ValueError('Agent revoked; an already issued operation may have completed')
                    result=self.store.read_json('agents/results/'+task_id+'.json.enc')
                    tasks=self.read_tasks(row['agent_id'])
                    task=next((t for t in tasks if t['id']==task_id),None)
                    if result:break
                    if job.get('cancel_requested') and task and task['state']=='pending':
                        task['state']='cancelled';self.save_tasks(row['agent_id'],tasks)
                        return {**row,'status':'cancelled','message':'Agent task cancelled before issue'}
                    if task and task['state']=='cancelled':return {**row,'status':'cancelled'}
                    if not task or time.time()>task['expires']:raise ValueError('Agent did not return a result before timeout; execution may be unknown')
                time.sleep(.2)
            else:raise ValueError('Agent result unavailable; execution may be unknown')
            data=result.get('result',{})
            if not isinstance(data,dict):raise ValueError('Invalid agent result')
            if result['status']=='failed':return {**row,'status':'failed','error':str(result.get('error','Agent operation failed'))[:1500],'result':data}
            if job['kind']=='ci_inventory':
                observation={**data,**windows_smt(data.get('cpu_topology'))}
                observation={k:observation.get(k) for k in AUTO_FIELDS}
                with self.lock:self.service.ci_registry().observe(row,observation)
                data=observation
            if job['kind']=='connections':
                from monitoring.connections import parse_netstat
                data={'connections':parse_netstat(data.get('stdout','')),'warning':data.get('stderr','')}
            if job['kind']=='transfer':
                from server.files import LIMIT
                if job['options']['direction']=='upload':
                    content=base64.b64decode(data.pop('content',''),validate=True)
                    if len(content)>LIMIT or hashlib.sha256(content).hexdigest()!=data.get('sha256'):raise ValueError('Agent file checksum failed')
                    path=job['options']['server_path'].replace('{hostname}',row['hostname'])
                    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    try:
                        with os.fdopen(fd,'wb') as output:output.write(content);output.flush();os.fsync(output.fileno())
                    except Exception:
                        Path(path).unlink(missing_ok=True);raise
                elif data.get('sha256')!=task.get('expected_sha256'):raise ValueError('Agent destination checksum failed')
            return {**row,'status':'completed','result':data}
        except Exception as exc:
            if job['kind']=='ci_inventory':
                with self.lock:self.service.ci_registry().observe(row,error=str(exc))
            return {**row,'status':'failed','error':str(exc)[:1500]}

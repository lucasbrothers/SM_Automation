"""Authorized WSL-only acceptance; temporary SSH account is removed in finally."""
import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from engine.ssh import SSHClient
from server.key_deploy import deploy
from server.files import transfer
from account.manager import manage_accounts


def check_su(user, key, directory):
    """Private mount namespace provides a test root password without changing host shadow."""
    import hashlib
    import socket
    import time
    import paramiko
    shadow = Path('/etc/shadow'); before = shadow.read_bytes()
    secret = secrets.token_urlsafe(32)
    hashed = subprocess.run(['openssl','passwd','-6','-stdin'],input=secret.encode(),capture_output=True,check=True).stdout.decode().strip()
    rows = before.decode().splitlines()
    for index,row in enumerate(rows):
        if row.startswith('root:'):
            fields=row.split(':');fields[1]=hashed;rows[index]=':'.join(fields)
    isolated=Path(directory)/'shadow';isolated.write_text('\n'.join(rows)+'\n');isolated.chmod(0o600)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    conf=Path(directory)/'sshd.conf'
    conf.write_text('Port '+str(port)+'\nListenAddress 127.0.0.1\nHostKey /etc/ssh/ssh_host_ed25519_key\nUsePAM no\nPermitRootLogin no\nPasswordAuthentication no\nPubkeyAuthentication yes\nAuthorizedKeysFile .ssh/authorized_keys\nAllowUsers '+user+'\nPidFile '+directory+'/sshd.pid\n')
    process=subprocess.Popen(['unshare','--mount','--propagation','private','sh','-c','mount --bind "$1" /etc/shadow && exec /usr/sbin/sshd -D -f "$2"','sh',str(isolated),str(conf)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=SSHClient('su-acceptance','127.0.0.1',user=user,key_filename=key,port=port)
    try:
        deadline=time.monotonic()+10
        while True:
            if process.poll() is not None:raise RuntimeError('Private test SSH namespace could not start')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.05)
        native=paramiko.SSHClient();native.set_missing_host_key_policy(paramiko.RejectPolicy())
        parts=Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
        import base64
        native.get_host_keys().add('[127.0.0.1]:'+str(port),'ssh-ed25519',paramiko.Ed25519Key(data=base64.b64decode(parts[1])))
        native.connect('127.0.0.1',port=port,username=user,key_filename=str(key),allow_agent=False,look_for_keys=False)
        client._client=native
        # No sudo password is supplied, so sudo must fail before su starts.
        result=client.execute_root('id -u', '', secret)
        assert result['exit_code']==0 and result['stdout'].splitlines()[0]=='0'
        assert secret not in str(result)
        print('PASS: real su fallback in private WSL namespace; host root password unchanged')
    finally:
        client.close();process.terminate();process.wait(timeout=10)
        assert hashlib.sha256(shadow.read_bytes()).digest()==hashlib.sha256(before).digest()


def main():
    if sys.platform != 'linux' or os.geteuid() != 0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Only approved local WSL root may run this acceptance tool')
    user = 'smcheck_' + uuid.uuid4().hex[:10]
    password = secrets.token_urlsafe(32)
    policy = Path('/etc/sudoers.d') / user
    created = False
    run = lambda args, **kw: subprocess.run(args, check=True, capture_output=True, **kw)
    try:
        run(['useradd', '-m', '-s', '/bin/bash', user]); created = True
        run(['chpasswd'], input=(user+':'+password+'\n').encode())
        policy.write_text(user+' ALL=(root) ALL\n'); policy.chmod(0o440)
        run(['visudo', '-cf', str(policy)])
        client = SSHClient('acceptance', '127.0.0.1', user=user, password=password)
        try:
            result = client.execute_root('id -u', password)
            assert result['exit_code'] == 0 and result['stdout'].strip() == '0'
            failed = client.execute_root('printf command-started; exit 7', password)
            assert failed['exit_code'] == 7 and failed['stdout'] == 'command-started'
            print('PASS: real password SSH, sudo root, command nonzero exit')
            with tempfile.TemporaryDirectory(prefix='sm-acceptance-') as directory:
                key = Path(directory)/'login.key'
                first = deploy(client, key); second = deploy(client, key)
                assert not first['already_present'] and second['already_present']
                print('PASS: first public key deployment, key authentication, idempotency')
                client.close()
                client = SSHClient('acceptance','127.0.0.1',user=user,key_filename=key)
                content = b'CLIENT-SERVER-roundtrip\x00\xff'
                source = Path('/home')/user/'source.bin'; source.write_bytes(content)
                import pwd
                account=pwd.getpwnam(user);os.chown(source,account.pw_uid,account.pw_gid)
                server_path=Path(directory)/'server.bin'; target=Path('/home')/user/'download.bin'
                transfer(client,{'direction':'upload','client_path':str(source),'server_path':str(server_path)})
                transfer(client,{'direction':'download','client_path':str(target),'server_path':str(server_path)})
                assert server_path.read_bytes()==target.read_bytes()==content
                print('PASS: CLIENT SERVER SFTP binary roundtrip')
                check_su(user, key, directory)
                rows=manage_accounts(client,{'action':'list'},'direct',user,30)['accounts']
                assert any(row['username']==user for row in rows)
                print('PASS: account list through non-root SSH login')
        finally: client.close()
    finally:
        policy.unlink(missing_ok=True)
        if created:
            subprocess.run(['pkill','-u',user], capture_output=True)
            import time
            time.sleep(0.3)
            run(['userdel','-r',user])
    print('PASS: temporary account and privilege policy removed; existing credentials unchanged')

if __name__ == '__main__': main()

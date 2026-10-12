"""Install only the configured SERVER public key for the SSH login account."""
import base64
import os
import stat
import uuid
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import paramiko

def ensure_key(path):
    path=Path(path).expanduser()
    if not path.exists():
        content=ed25519.Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption())
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(content)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("SERVER private key must be a protected regular file")
    key=paramiko.PKey.from_path(path)
    return key.get_name()+' '+base64.b64encode(key.asbytes()).decode()

def deploy(client,path):
    public=ensure_key(path)
    if client._client is None:client.connect()
    with client._client.open_sftp() as sftp:
        sftp.get_channel().settimeout(client.timeout)
        home=sftp.normalize('.')
        directory=home.rstrip('/')+'/.ssh'; target=directory+'/authorized_keys'
        try:info=sftp.lstat(directory)
        except FileNotFoundError:
            sftp.mkdir(directory,0o700);info=sftp.lstat(directory)
        if not stat.S_ISDIR(info.st_mode):raise ValueError("CLIENT .ssh must be a real directory")
        try:
            info=sftp.lstat(target)
        except FileNotFoundError:info=None
        content=b''
        if info:
            if not stat.S_ISREG(info.st_mode) or info.st_size>1024*1024:raise ValueError("CLIENT authorized_keys must be a regular file up to 1 MiB")
            with sftp.open(target,'rb') as stream:content=stream.read(1024*1024+1)
            if len(content)>1024*1024:raise ValueError("CLIENT authorized_keys grew beyond limit")
        blob=public.split()[1]
        present=any(blob in line.split() for line in content.decode('utf-8',errors='replace').splitlines())
        if not present:
            temporary=directory+'/.sm-key-'+uuid.uuid4().hex
            try:
                with sftp.open(temporary,'wx') as stream:stream.write(content+(b'\n' if content and not content.endswith(b'\n') else b'')+public.encode()+b'\n')
                sftp.chmod(temporary,0o600)
                if info:sftp.posix_rename(temporary,target)
                else:sftp.rename(temporary,target)
            finally:
                try:sftp.remove(temporary)
                except OSError:pass
        sftp.chmod(directory,0o700);sftp.chmod(target,0o600)
    probe=type(client)(client.hostname,client.ip,user=client.user,key_filename=path,port=client.port,timeout=client.timeout)
    try:probe.connect()
    finally:probe.close()
    return {"status":"completed","account":client.user,"public_key_installed":True,"already_present":present,"key_login_verified":True}

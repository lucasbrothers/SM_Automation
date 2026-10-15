"""Isolated local WSL SSH acceptance; never alters an existing account or host key."""
import os,secrets,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from engine.ssh import SSHClient
from server.key_deploy import deploy
import paramiko

def main():
 if sys.platform!="linux" or os.geteuid()!=0 or "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():raise RuntimeError("Use approved local WSL root only")
 user="smkey"+uuid.uuid4().hex[:10];created=False;process=None;old_home=os.environ.get("HOME")
 def run(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,**kwargs)
 with tempfile.TemporaryDirectory(prefix="sm-hostkey-") as directory:
  folder=Path(directory)
  try:
   run(["useradd","-m","-s","/bin/sh",user]);created=True
   # Use a fresh password only in process memory for the initial authenticated connection.
   password=secrets.token_urlsafe(32);run(["chpasswd"],input=(user+":"+password+"\n").encode())
   hostkey=folder/"hostkey";run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(hostkey)])
   with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
   config=folder/"sshd.conf";config.write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {hostkey}\nPidFile {folder}/sshd.pid\nUsePAM no\nPasswordAuthentication yes\nPubkeyAuthentication yes\nAllowUsers {user}\nSubsystem sftp internal-sftp\n")
   process=subprocess.Popen(["/usr/sbin/sshd","-D","-f",str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   for _ in range(100):
    try:
     with socket.create_connection(("127.0.0.1",port),timeout=.1):break
    except OSError:time.sleep(.05)
   os.environ["HOME"]=str(folder)
   client=SSHClient("isolated-key-client","127.0.0.1",user=user,password=password,port=port)
   client.accept_new_host_key=True
   try:
    result=deploy(client,folder/"server-key")
    assert result["key_login_verified"] and result["host_key_registered"]
   finally:client.close()
   probe=SSHClient("isolated-key-client","127.0.0.1",user=user,key_filename=folder/"server-key",port=port)
   try:assert probe.execute("id -un").strip()==user
   finally:probe.close()
   wrong=paramiko.HostKeys();wrong.add("[127.0.0.1]:"+str(port),"ssh-ed25519",paramiko.Ed25519Key.from_private_key_file(str(hostkey)))
   other=folder/"changed";run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(other)])
   wrong.add("[127.0.0.1]:"+str(port),"ssh-ed25519",paramiko.Ed25519Key.from_private_key_file(str(other)));wrong.save(str(folder/".ssh/known_hosts"))
   before=(folder/".ssh/known_hosts").read_bytes();bad=SSHClient("isolated-key-client","127.0.0.1",user=user,password=password,port=port);bad.accept_new_host_key=True
   try:
    try:bad.connect()
    except paramiko.BadHostKeyException:pass
    else:raise AssertionError("Changed host key was accepted")
   finally:bad.close()
   assert (folder/".ssh/known_hosts").read_bytes()==before
   print("PASS first-contact auto trust, public-key deployment, key-only reconnect and changed-host-key rejection",flush=True)
  finally:
   if old_home is None:os.environ.pop("HOME",None)
   else:os.environ["HOME"]=old_home
   if process:process.terminate();process.wait(timeout=10)
   if created:
    for attempt in range(50):
     deleted=subprocess.run(["userdel","-r",user],capture_output=True)
     if deleted.returncode==0:break
     if deleted.returncode!=8:raise RuntimeError("Temporary SSH account cleanup failed")
     subprocess.run(["pkill","-TERM","-u",user],capture_output=True);time.sleep(.1)
    else:raise RuntimeError("Temporary SSH account still has active sessions")

if __name__=="__main__":main()

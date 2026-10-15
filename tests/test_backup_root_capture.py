from types import SimpleNamespace
import re
import pytest
from engine import remote


def test_sudo_root_binary_capture_uses_stdin_and_preserves_stderr(monkeypatch):
    calls=[]
    def capture(client,command,**kw):
        calls.append((command,kw))
        marker=re.search(r'__SM_BACKUP_ROOT_[a-f0-9]+__',command).group()
        return remote.CommandResult(b"tar\x00\xff",'Could not chdir to home directory /home/test: No such file or directory\n'+marker+'\n',0)
    monkeypatch.setattr(remote,'capture',capture)
    result=remote.capture_root(SimpleNamespace(user='login'),'tar -cf - /etc/hosts',login_password='fixture-secret')
    assert result.stdout==b'tar\x00\xff'
    assert 'fixture-secret' not in calls[0][0] and calls[0][1]['input_data']==b'fixture-secret\n'
    assert '__SM_BACKUP_ROOT_' not in result.stderr
    assert 'Could not chdir' in result.stderr


def test_su_fallback_only_before_root_command_started(monkeypatch):
    calls=[]
    def capture(client,command,**kw):
        calls.append(command)
        if len(calls)==1:return remote.CommandResult(b'', 'sudo: authentication failed',1)
        marker=re.search(r'__SM_BACKUP_ROOT_[a-f0-9]+__',command).group()
        return remote.CommandResult(b'partial','Password: '+marker+'\npermission denied',1)
    monkeypatch.setattr(remote,'capture',capture)
    value=remote.capture_root(SimpleNamespace(user='login'),'echo fixture',root_password='root-fixture')
    assert len(calls)==2 and 'su - root' in calls[1] and 'root-fixture' not in calls[1]
    assert value.exit_code==1 and 'permission denied' in value.stderr


def test_root_transition_failure_never_accepts_unprivileged_capture(monkeypatch):
    monkeypatch.setattr(remote,'capture',lambda *a,**k:remote.CommandResult(b'not root','denied',1))
    with pytest.raises(remote.SSHCommandError,match='root transition failed'):remote.capture_root(SimpleNamespace(user='login'),'id')

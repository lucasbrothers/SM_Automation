import re
from unittest.mock import Mock
from engine.ssh import SSHClient

def test_sudo_command_failure_does_not_retry_su():
    client=SSHClient("lab","127.0.0.1",user="operator")
    def run(command,**kwargs):
        marker=re.search(r"__SM_ROOT_[a-f0-9]+__",command)[0]
        assert "/dev/null" in command
        return {"stdout":marker+"\npartial","stderr":"command error","exit_code":7}
    client.execute_result=Mock(side_effect=run)
    result=client.execute_root("false","synthetic","synthetic-root")
    assert result["exit_code"]==7 and result["stdout"]=="partial"
    assert client.execute_result.call_count==1

def test_su_only_after_sudo_transition_failed():
    client=SSHClient("lab","127.0.0.1",user="operator")
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        if len(calls)==1:return {"stdout":"","stderr":"sudo denied","exit_code":1}
        assert kwargs["password_prompt"] and "stty -echo" in command
        marker=re.search(r"__SM_ROOT_[a-f0-9]+__",command)[0]
        return {"stdout":"Password: "+marker+"\r\nroot\r\n","stderr":"","exit_code":0}
    client.execute_result=run
    assert client.execute_root("whoami","synthetic","synthetic-root")["stdout"]=="root\r\n"
    assert len(calls)==2 and "synthetic-root" not in calls[1][0]

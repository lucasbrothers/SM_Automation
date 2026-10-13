from cryptography.fernet import Fernet
import pytest
from server.commands import library
from storage.encrypted import EncryptedStore


def test_command_library_persists_updates_and_deletes_encrypted(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    store=EncryptedStore(tmp_path/'data',key)
    command='printf example-command\nprintf second-line'
    library(store,'command.saved.save',{'name':'Daily check','command':command})
    assert command.encode() not in (store.root/'saved-commands.json.enc').read_bytes()
    reopened=EncryptedStore(store.root,key)
    assert library(reopened,'command.saved.list',{})==[{'name':'Daily check','command':command}]
    library(reopened,'command.saved.save',{'name':'Daily check','command':'id -u'})
    assert library(store,'command.saved.list',{})==[{'name':'Daily check','command':'id -u'}]
    library(store,'command.saved.delete',{'name':'Daily check'})
    assert library(reopened,'command.saved.list',{})==[]


@pytest.mark.parametrize('params',[{'name':'','command':'id'},{'name':'x','command':''},{'name':'x\n','command':'id'},{'name':'x','command':'id\x00'}])
def test_invalid_saved_commands_rejected(tmp_path,params):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    with pytest.raises(ValueError):library(EncryptedStore(tmp_path/'data',key),'command.saved.save',params)

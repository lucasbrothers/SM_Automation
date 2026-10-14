import pytest
from server.auth import authorize,save_account,role_for,authenticate
from storage.encrypted import EncryptedStore
from cryptography.fernet import Fernet

@pytest.mark.parametrize('method,params', [('gui.account.save',{}),('gui.account.list',{}),('inventory.save',{}),('client.credentials.save',{}),('schedule.create',{}),('job.start',{'kind':'security_apply'}),('job.start',{'kind':'accounts','options':{'action':'delete'}})])
@pytest.mark.parametrize('role',['operator','viewer'])
def test_non_admin_cannot_manage_security_accounts_or_inventory(role,method,params):
    with pytest.raises(ValueError,match='Permission denied'):authorize(role,method,params)

@pytest.mark.parametrize('method',['file.upload','file.mkdir','file.commit','file.abort','job.start','command.saved.save'])
def test_viewer_cannot_mutate(method):
    with pytest.raises(ValueError):authorize('viewer',method,{'kind':'command'})


def test_roles_keep_last_admin_and_role_edit_keeps_password(tmp_path):
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key());key.chmod(0o600)
    store=EncryptedStore(tmp_path/'data',key)
    save_account(store,'admin','synthetic-admin')
    save_account(store,'worker','synthetic-worker','operator')
    assert role_for(store,'worker')=='operator'
    save_account(store,'worker','','viewer')
    assert authenticate(store,'worker','synthetic-worker') and role_for(store,'worker')=='viewer'
    with pytest.raises(ValueError,match='administrator'):save_account(store,'admin','','viewer')
    assert role_for(store,'admin')=='admin'
    with pytest.raises(ValueError):authorize('operator','job.start',{'kind':'command'})
    authorize('viewer','file.download',{'path':'/srv/sm-automation/shared/example'})
    with pytest.raises(ValueError):authorize('viewer','file.download',{'path':'/root/.config/sm-automation/api.token'})

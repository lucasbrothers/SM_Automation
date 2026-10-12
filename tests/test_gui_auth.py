from cryptography.fernet import Fernet
from server.auth import save_account, authenticate
from storage.encrypted import EncryptedStore

def test_login_hashing_and_generic_rejection(tmp_path):
    key=tmp_path / "key"; key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    store=EncryptedStore(tmp_path / "data", key)
    password=Fernet.generate_key().decode()
    assert save_account(store,"tester",password)=={"id":"tester"}
    assert authenticate(store,"tester",password)
    assert not authenticate(store,"tester","invalid")
    assert not authenticate(store,"unknown",password)
    record=store.read_json("gui-accounts.json.enc")["tester"]
    assert password not in str(record) and password.encode() not in store.path("gui-accounts.json.enc").read_bytes()
    old_hash=record["hash"]
    save_account(store,"tester",password)
    assert store.read_json("gui-accounts.json.enc")["tester"]["hash"]!=old_hash

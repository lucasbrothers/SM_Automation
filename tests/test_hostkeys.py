from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import paramiko
import pytest
from engine.hostkeys import AcceptNewHostKey

def test_first_key_is_persisted_and_repeated_key_is_not_replaced(tmp_path):
    path=tmp_path/"known_hosts";owner=SimpleNamespace(host_key_registered=False)
    key=paramiko.RSAKey.generate(1024);client=paramiko.SSHClient()
    AcceptNewHostKey(path,owner).missing_host_key(client,"[127.0.0.1]:2222",key)
    assert owner.host_key_registered and owner.host_key_fingerprint.startswith("SHA256:")
    assert paramiko.HostKeys(str(path)).check("[127.0.0.1]:2222",key)
    before=path.read_bytes();owner.host_key_registered=False
    AcceptNewHostKey(path,owner).missing_host_key(client,"[127.0.0.1]:2222",key)
    assert not owner.host_key_registered and path.read_bytes()==before
    with pytest.raises(paramiko.BadHostKeyException):AcceptNewHostKey(path,owner).missing_host_key(client,"[127.0.0.1]:2222",paramiko.RSAKey.generate(1024))
    assert path.read_bytes()==before

def test_parallel_first_keys_preserve_all_hosts(tmp_path):
    key=paramiko.RSAKey.generate(1024);path=tmp_path/"known_hosts"
    def add(i):AcceptNewHostKey(path,SimpleNamespace()).missing_host_key(paramiko.SSHClient(),"host"+str(i),key)
    with ThreadPoolExecutor(max_workers=4) as workers:list(workers.map(add,range(10)))
    assert len(paramiko.HostKeys(str(path)))==10

def test_existing_symlink_not_overwritten(tmp_path):
    path=tmp_path/"known_hosts";destination=tmp_path/"other";destination.write_text("unchanged")
    try:path.symlink_to(destination)
    except OSError:pytest.skip("Symlink permission unavailable")
    with pytest.raises(ValueError):AcceptNewHostKey(path,SimpleNamespace()).missing_host_key(paramiko.SSHClient(),"host",paramiko.RSAKey.generate(1024))
    assert destination.read_text()=="unchanged"


def test_different_algorithm_cannot_replace_existing_host_identity(tmp_path):
    path=tmp_path/"known_hosts";client=paramiko.SSHClient();owner=SimpleNamespace()
    AcceptNewHostKey(path,owner).missing_host_key(client,"host",paramiko.RSAKey.generate(1024))
    before=path.read_bytes()
    with pytest.raises(paramiko.BadHostKeyException):AcceptNewHostKey(path,owner).missing_host_key(client,"host",paramiko.ECDSAKey.generate())
    assert path.read_bytes()==before


def test_key_verification_does_not_fall_back_to_agent_or_other_keys(monkeypatch):
    from unittest.mock import Mock
    from engine.ssh import SSHClient
    native=Mock();monkeypatch.setattr("engine.ssh.paramiko.SSHClient",lambda:native)
    client=SSHClient("host","127.0.0.1",key_filename="selected-key");client.key_only=True
    client.connect()
    assert native.connect.call_args.kwargs["allow_agent"] is False
    assert native.connect.call_args.kwargs["look_for_keys"] is False
    client.close()

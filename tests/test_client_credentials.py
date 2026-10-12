from types import SimpleNamespace
import threading
import pytest
from cryptography.fernet import Fernet
from storage.encrypted import EncryptedStore
from server.service import ManagementService

@pytest.fixture
def service(tmp_path):
    key = tmp_path / "key"; key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
    service = ManagementService.__new__(ManagementService)
    service.data = EncryptedStore(tmp_path / "data", key)
    service.lock = threading.RLock(); service.jobs = {}; service.profiles = {}
    service.config = SimpleNamespace(ssh_user="root", ssh_port=22)
    service.data.write_json("inventory.json.enc", [{"hostname": "lab", "ip": "127.0.0.1", "os": "Linux", "profile": "default"}])
    return service

def test_password_encrypted_not_returned_and_blank_retains(service):
    params = dict(hostname="lab", user="operator", port=22, use_password=True, password="synthetic-test-value")
    result = service.credentials_save(params)
    assert result["password_saved"] and "password" not in result
    assert b"synthetic-test-value" not in service.data.path("client-credentials.json.enc").read_bytes()
    service.credentials_save({**params, "password": ""})
    assert service.data.read_json("client-credentials.json.enc")["lab"]["password"] == params["password"]
    service.credentials_save({**params, "use_password": False, "password": ""})
    assert not service.credentials_get("lab")["password_saved"]

def test_changed_ip_ignores_saved_credentials(service):
    service.credentials_save(dict(hostname="lab", user="operator", port=2222, use_password=False))
    service.data.write_json("inventory.json.enc", [{"hostname": "lab", "ip": "127.0.0.2", "os": "Linux"}])
    assert service.credentials_get("lab")["user"] == "root"

def test_active_job_blocks_credential_changes(service):
    service.jobs = {"job": {"status": "running", "targets": [{"hostname": "lab"}]}}
    with pytest.raises(ValueError):
        service.credentials_save(dict(hostname="lab", user="operator", port=22))

@pytest.mark.parametrize("change", [{"user": ""}, {"port": True}, {"port": 0}, {"password": 5}, {"use_password": "yes"}])
def test_invalid_settings_rejected(service, change):
    with pytest.raises(ValueError):
        service.credentials_save({"hostname": "lab", "user": "operator", "port": 22, **change})

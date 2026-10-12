import pytest
from server.files import validate

@pytest.mark.parametrize("params", [
    {}, {"direction": "wrong", "server_path": "/tmp/a", "client_path": "/tmp/b"},
    {"direction": "upload", "server_path": "relative", "client_path": "/tmp/b"},
    {"direction": "download", "server_path": "/tmp/a", "client_path": "relative"},
    {"direction": "download", "server_path": "/tmp/a", "client_path": "/tmp/b\x00"},
])
def test_invalid_transfer_options_rejected(params):
    with pytest.raises(ValueError):
        validate(params)

def test_transfer_paths_preserve_roles():
    params = {"direction": "upload", "server_path": "/srv/inbox/a", "client_path": "/home/user/a"}
    assert validate(params) == params

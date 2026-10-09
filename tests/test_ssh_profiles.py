import json
import pytest
from server.service import load_ssh_profiles


@pytest.mark.parametrize("profile", [{"port": True}, {"port": 0}, {"port": "22"},
                                    {"key_file": "relative/key"}, {"user": ""},
                                    {"privilege": "invalid"}, {"password_env": "BAD NAME"},
                                    {"password": "synthetic-secret"}])
def test_invalid_profile_rejected_without_exposing_values(tmp_path, profile):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"lab": profile})); path.chmod(0o600)
    with pytest.raises(ValueError) as error:
        load_ssh_profiles(path)
    assert "synthetic-secret" not in str(error.value)


def test_valid_profile_and_missing_file(tmp_path):
    path = tmp_path / "profiles.json"
    assert load_ssh_profiles(path) == {}
    profiles = {"lab": {"user": "root", "port": 22, "key_file": "~/.ssh/lab", "privilege": "direct", "password_env": "LAB_PASSWORD"}}
    path.write_text(json.dumps(profiles)); path.chmod(0o600)
    assert load_ssh_profiles(path) == profiles

import pytest

from security.policy import evaluate_record


BASE_RECORD = {
    "hostname": "TEST01",
    "ip": "192.0.2.10",
    "status": "passed",
    "root_accounts": ["root"],
    "sshd_settings": {
        "permitrootlogin": "without-password",
        "passwordauthentication": "no",
        "pubkeyauthentication": "yes",
    },
    "sshd_config_mode": "600 root root",
}


POLICY = {
    "allowed_sshd_settings": {
        "permitrootlogin": ["without-password", "no"],
        "pubkeyauthentication": ["yes"],
    },
    "allowed_sshd_config_modes": ["600"],
    "required_root_accounts": ["root"],
    "forbidden_root_accounts": [],
}


def test_compliant_record_passes():
    result = evaluate_record(BASE_RECORD, POLICY)

    assert result["status"] == "passed"
    assert result["findings"] == []


def test_disallowed_setting_is_reported():
    record = {**BASE_RECORD, "sshd_settings": {"permitrootlogin": "yes"}}

    result = evaluate_record(record, POLICY)

    assert result["status"] == "failed"
    assert "permitrootlogin='yes' is not allowed" in result["findings"]


def test_unsupported_setting_is_rejected():
    with pytest.raises(ValueError, match="Unsupported SSH policy setting"):
        evaluate_record(BASE_RECORD, {"allowed_sshd_settings": {"unknown": ["yes"]}})

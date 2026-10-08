from desktop.security import audit_rows


def test_failed_collection_is_not_reported_as_compliant():
    rows = audit_rows([{"hostname": "lab", "status": "failed", "error": "SSH failed"}])
    assert rows == [["lab", "Collection", "SSH failed", "Unavailable"]]


def test_extra_root_and_password_authentication_require_review():
    rows = audit_rows([{"hostname": "lab", "status": "completed", "result": {
        "root_accounts": ["root", "extra"], "sshd_settings": {"permitrootlogin": "prohibit-password", "passwordauthentication": "yes", "pubkeyauthentication": "yes"}, "sshd_config_mode": "600 root root"}}])
    assert rows[0][-1] == "Review"
    assert rows[1][-1] == "OK"
    assert rows[2][-1] == "Review"

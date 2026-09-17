from security.audit import _root_accounts, _sshd_settings


def test_root_accounts_returns_unique_uid_zero_users():
    output = "root:x:0:0:root:/root:/bin/bash\nbackup:x:1000:1000:backup:/home/backup:/bin/bash\nroot:x:0:0:duplicate:/root:/bin/bash\n"

    assert _root_accounts(output) == ("root",)


def test_sshd_settings_extracts_supported_values():
    output = """permitrootlogin without-password
passwordauthentication yes
pubkeyauthentication yes
unsupported value
"""

    assert _sshd_settings(output) == {
        "permitrootlogin": "without-password",
        "passwordauthentication": "yes",
        "pubkeyauthentication": "yes",
    }


def test_missing_sshd_observations_fail_audit():
    import pytest
    from security.audit import audit_linux_server
    class Client:
        def execute(self, command):
            return ""
    with pytest.raises(ValueError, match="observations"):
        audit_linux_server(Client())

from security.remediation import build_remediation_plan


def test_remediation_plan_lists_only_noncompliant_settings():
    records = [{
        "hostname": "TEST01",
        "ip": "192.0.2.10",
        "sshd_settings": {
            "permitrootlogin": "yes",
            "pubkeyauthentication": "yes",
        },
    }]
    policy = {
        "allowed_sshd_settings": {
            "permitrootlogin": ["no"],
            "pubkeyauthentication": ["yes"],
        }
    }

    result = build_remediation_plan(records, policy)

    assert result[0]["status"] == "action_required"
    assert result[0]["actions"] == [{
        "type": "set_sshd_option",
        "parameter": "permitrootlogin",
        "current": "yes",
        "recommended": "no",
    }]


def test_compliant_server_has_no_actions():
    result = build_remediation_plan(
        [{"hostname": "TEST02", "ip": "192.0.2.11", "sshd_settings": {"pubkeyauthentication": "yes"}}],
        {"allowed_sshd_settings": {"pubkeyauthentication": ["yes"]}},
    )

    assert result[0]["status"] == "compliant"
    assert result[0]["actions"] == []
from security.remediation import build_remediation_plan


def test_remediation_plan_lists_only_noncompliant_settings():
    records = [{
        "hostname": "TEST01",
        "status": "passed",
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
        [{"status": "passed", "hostname": "TEST02", "ip": "192.0.2.11", "sshd_settings": {"pubkeyauthentication": "yes"}}],
        {"allowed_sshd_settings": {"pubkeyauthentication": ["yes"]}},
    )

    assert result[0]["status"] == "no_changes"
    assert result[0]["actions"] == []

def test_failed_or_missing_audit_never_generates_actions():
    for status in (None, "failed"):
        result = build_remediation_plan(
            [{"hostname": "TEST", "ip": "192.0.2.1", "status": status,
              "sshd_settings": {"permitrootlogin": "yes"}}],
            {"allowed_sshd_settings": {"permitrootlogin": ["no"]}},
        )[0]
        assert result["status"] == "blocked"
        assert result["actions"] == []


def test_missing_observation_blocks_entire_host():
    result = build_remediation_plan(
        [{"hostname": "TEST", "ip": "192.0.2.1", "status": "passed",
          "sshd_settings": {"permitrootlogin": "yes"}}],
        {"allowed_sshd_settings": {"permitrootlogin": ["no"], "pubkeyauthentication": ["yes"]}},
    )[0]
    assert result["status"] == "blocked"
    assert result["actions"] == []

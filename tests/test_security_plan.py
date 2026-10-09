import pytest
from security.plan import verify_observations


def observations():
    return {"sshd_settings": {"pubkeyauthentication": "yes"}, "sshd_config_mode": "600 root root", "root_accounts": ["root"]}


def test_serialized_root_list_matches_audit_tuple():
    actual = observations(); actual["root_accounts"] = ("root",)
    verify_observations(observations(), actual)


def test_no_change_plan_rejects_authentication_drift():
    actual = observations(); actual["sshd_settings"] = {"pubkeyauthentication": "no"}
    with pytest.raises(ValueError, match="changed since planning"):
        verify_observations(observations(), actual)


def test_missing_observations_are_not_accepted():
    with pytest.raises(ValueError, match="Incomplete"):
        verify_observations({}, observations())

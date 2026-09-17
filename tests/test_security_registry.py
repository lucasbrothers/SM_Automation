import json

import pytest

from security.registry import PolicyRegistryError, load_policy, policy_path_for


def test_policy_path_for_supported_rhel9(tmp_path):
    assert policy_path_for("RHEL", "9", tmp_path).name == "security-policy-rhel9.json"


def test_policy_path_for_supported_windows2022(tmp_path):
    assert policy_path_for("windows", "2022", tmp_path).name == "security-policy-windows2022.json"


def test_policy_path_for_rejects_unsupported_version(tmp_path):
    with pytest.raises(PolicyRegistryError, match="Unsupported OS/version"):
        policy_path_for("rhel", "7", tmp_path)


def test_load_policy_requires_json_object(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(PolicyRegistryError, match="JSON object"):
        load_policy(path)
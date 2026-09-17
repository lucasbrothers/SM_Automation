from __future__ import annotations

from typing import Any
from typing import cast


SUPPORTED_SETTINGS = {
    "permitrootlogin",
    "passwordauthentication",
    "pubkeyauthentication",
}


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a list of strings")
        result.append(item)
    return result


def evaluate_record(record: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one security audit record against explicit policy rules."""
    findings: list[str] = []
    if record.get("status") != "passed":
        findings.append("audit did not complete")

    allowed_settings = policy.get("allowed_sshd_settings", {})
    for name, allowed_values in allowed_settings.items():
        if name not in SUPPORTED_SETTINGS:
            raise ValueError(f"Unsupported SSH policy setting: {name}")
        allowed_values = _string_list(allowed_values, f"allowed_sshd_settings.{name}")
        actual = record.get("sshd_settings", {}).get(name)
        if actual not in allowed_values:
            findings.append(f"{name}={actual!r} is not allowed")

    allowed_modes = policy.get("allowed_sshd_config_modes")
    if allowed_modes is not None:
        allowed_modes = _string_list(allowed_modes, "allowed_sshd_config_modes")
        actual_mode = str(record.get("sshd_config_mode", "")).split(" ", 1)[0]
        if actual_mode not in allowed_modes:
            findings.append(f"sshd_config_mode={actual_mode!r} is not allowed")

    required_accounts = _string_list(
        policy.get("required_root_accounts", []),
        "required_root_accounts",
    )
    actual_accounts = set(record.get("root_accounts", []))
    for account in required_accounts:
        if account not in actual_accounts:
            findings.append(f"required root account missing: {account}")

    forbidden_accounts = _string_list(
        policy.get("forbidden_root_accounts", []),
        "forbidden_root_accounts",
    )
    for account in forbidden_accounts:
        if account in actual_accounts:
            findings.append(f"forbidden root account present: {account}")

    return {
        "hostname": record.get("hostname"),
        "ip": record.get("ip"),
        "status": "passed" if not findings else "failed",
        "findings": findings,
    }


def evaluate_report(
    records: list[dict[str, Any]], policy: dict[str, Any]
) -> list[dict[str, Any]]:
    """Evaluate all records in an audit report."""
    return [evaluate_record(record, policy) for record in records]

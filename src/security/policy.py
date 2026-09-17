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
    if not isinstance(record, dict) or not isinstance(policy, dict):
        raise ValueError("Audit records and policy must be objects")
    allowed = policy.get("allowed_sshd_settings", {})
    controls = policy.get("security_controls", {})
    if not isinstance(allowed, dict) or not isinstance(controls, dict):
        raise ValueError("SSH settings and security_controls must be objects")
    evaluated: list[str] = []
    unevaluated = [f"security_controls.{name}" for name in controls]
    if policy.get("os") not in (None, "rhel", "linux"):
        return {
            "hostname": record.get("hostname"), "ip": record.get("ip"),
            "status": "not_evaluated", "findings": ["Platform evaluator is not implemented"],
            "evaluated_checks": [], "unevaluated_controls": unevaluated or ["platform"],
        }
    if not isinstance(record.get("sshd_settings", {}), dict):
        raise ValueError("sshd_settings must be an object")
    findings: list[str] = []
    if record.get("status") != "passed":
        findings.append("audit did not complete")

    allowed_settings = policy.get("allowed_sshd_settings", {})
    for name, allowed_values in allowed_settings.items():
        if name not in SUPPORTED_SETTINGS:
            raise ValueError(f"Unsupported SSH policy setting: {name}")
        allowed_values = _string_list(allowed_values, f"allowed_sshd_settings.{name}")
        if not allowed_values:
            raise ValueError(f"Policy values for {name} must not be empty")
        evaluated.append(f"allowed_sshd_settings.{name}")
        actual = record.get("sshd_settings", {}).get(name)
        if actual not in allowed_values:
            findings.append(f"{name}={actual!r} is not allowed")

    allowed_modes = policy.get("allowed_sshd_config_modes")
    if allowed_modes is not None:
        allowed_modes = _string_list(allowed_modes, "allowed_sshd_config_modes")
        evaluated.append("allowed_sshd_config_modes")
        actual_mode = str(record.get("sshd_config_mode", "")).split(" ", 1)[0]
        if actual_mode not in allowed_modes:
            findings.append(f"sshd_config_mode={actual_mode!r} is not allowed")

    required_accounts = _string_list(
        policy.get("required_root_accounts", []),
        "required_root_accounts",
    )
    actual_accounts = set(_string_list(record.get("root_accounts", []), "root_accounts"))
    if required_accounts or policy.get("forbidden_root_accounts"):
        evaluated.append("root_accounts")
        if "root_accounts" not in record:
            findings.append("root account observations are missing")
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
        "status": "failed" if findings else ("not_evaluated" if unevaluated or not evaluated else "passed"),
        "evaluated_checks": evaluated,
        "unevaluated_controls": unevaluated or ([] if evaluated else ["no supported checks"]),
        "findings": findings,
    }


def evaluate_report(
    records: list[dict[str, Any]], policy: dict[str, Any]
) -> list[dict[str, Any]]:
    """Evaluate all records in an audit report."""
    if not isinstance(records, list) or not records:
        raise ValueError("Audit report must contain at least one record")
    return [evaluate_record(record, policy) for record in records]

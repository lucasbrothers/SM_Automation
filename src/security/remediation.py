from __future__ import annotations

from typing import Any

from security.policy import evaluate_record


def build_remediation_plan(
    records: list[dict[str, Any]], policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Plan only observed SSH changes; incomplete audits cannot authorize writes."""
    if not isinstance(records, list) or not records:
        raise ValueError("Audit report must contain at least one record")
    allowed_settings = policy.get("allowed_sshd_settings", {})
    plans = []
    for record in records:
        evaluation = evaluate_record(record, policy)
        actual = record.get("sshd_settings", {})
        reasons = []
        if record.get("status") != "passed":
            reasons.append("Audit did not complete")
        if not record.get("hostname") or not record.get("ip"):
            reasons.append("Target identity is missing")
        if policy.get("os") not in (None, "rhel", "linux") or not allowed_settings:
            reasons.append("No supported SSH apply policy")
        if any(name not in {"permitrootlogin", "pubkeyauthentication"} for name in allowed_settings):
            reasons.append("Policy contains settings without an apply adapter")
        if any(not isinstance(actual.get(name), str) or not actual[name] for name in allowed_settings):
            reasons.append("Required SSH observations are missing")
        actions = []
        if not reasons:
            for name, values in allowed_settings.items():
                if actual[name] not in values:
                    actions.append({"type": "set_sshd_option", "parameter": name,
                                    "current": actual[name], "recommended": values[0]})
        plans.append({
            "hostname": record.get("hostname"), "ip": record.get("ip"),
            "status": "blocked" if reasons else ("action_required" if actions else "no_changes"),
            "scope": "sshd_settings", "actions": actions, "reasons": reasons,
            "compliance_status": evaluation["status"],
            "unevaluated_controls": evaluation["unevaluated_controls"],
        })
    return plans

from __future__ import annotations

from typing import Any


def build_remediation_plan(
    records: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a non-destructive plan for SSH settings outside the policy."""
    allowed_settings = policy.get("allowed_sshd_settings", {})
    plans: list[dict[str, Any]] = []
    for record in records:
        actions: list[dict[str, str]] = []
        actual_settings = record.get("sshd_settings", {})
        for name, allowed_values in allowed_settings.items():
            if not isinstance(allowed_values, list) or not allowed_values:
                raise ValueError(f"Policy values for {name} must be a nonempty list")
            actual = actual_settings.get(name)
            recommended = allowed_values[0]
            if actual not in allowed_values:
                actions.append({
                    "type": "set_sshd_option",
                    "parameter": name,
                    "current": str(actual),
                    "recommended": recommended,
                })
        plans.append({
            "hostname": record.get("hostname"),
            "ip": record.get("ip"),
            "status": "action_required" if actions else "compliant",
            "actions": actions,
        })
    return plans
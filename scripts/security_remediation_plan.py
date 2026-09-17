from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from security.remediation import build_remediation_plan


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Cannot read JSON file: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a non-destructive security remediation plan."
    )
    parser.add_argument("--audit-report", required=True)
    parser.add_argument("--policy-file", required=True)
    parser.add_argument("--report-file", required=True)
    args = parser.parse_args()

    try:
        audit_report = _read_json(Path(args.audit_report))
        policy = _read_json(Path(args.policy_file))
        if not isinstance(audit_report, list) or not isinstance(policy, dict):
            raise ValueError("Audit report must be a list and policy must be an object.")
        plan = build_remediation_plan(audit_report, policy)
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    report_path = Path(args.report_file).resolve()
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(plan, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Report write failed: {exc}", file=sys.stderr)
        return 2

    action_count = 0
    for server in plan:
        actions = server["actions"]
        action_count += len(actions)
        print(f"[{server['status'].upper()}] {server['hostname']} ({server['ip']})")
        for action in actions:
            print(
                f"       set {action['parameter']}: "
                f"{action['current']} -> {action['recommended']}"
            )
    print(f"Plan: {report_path}")
    print(f"Summary: {action_count} action(s) required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
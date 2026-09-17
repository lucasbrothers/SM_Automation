from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from security.policy import evaluate_report
from security.registry import PolicyRegistryError, load_policy, policy_path_for


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Cannot read JSON file: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a security audit report against an explicit policy."
    )
    parser.add_argument("--audit-report", required=True, help="Security audit JSON report")
    policy_group = parser.add_mutually_exclusive_group(required=True)
    policy_group.add_argument("--policy-file", help="Security policy JSON file")
    policy_group.add_argument("--os", help="Target operating system, for example rhel")
    parser.add_argument("--version", help="Target OS version when using --os")
    parser.add_argument("--report-file", help="Optional compliance report JSON path")
    args = parser.parse_args()

    try:
        audit_report = _read_json(Path(args.audit_report))
        if args.policy_file:
            policy = load_policy(args.policy_file)
        elif not args.version:
            raise PolicyRegistryError("--version is required when using --os.")
        else:
            policy = load_policy(
                policy_path_for(args.os, args.version, ROOT / "config")
            )
        if not isinstance(audit_report, list) or not isinstance(policy, dict):
            raise ValueError("Audit report must be a list and policy must be an object.")
        results = evaluate_report(audit_report, policy)
    except (PolicyRegistryError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    failed = 0
    for result in results:
        if result["status"] == "passed":
            print(f"[PASS] {result['hostname']} ({result['ip']})")
        else:
            failed += 1
            print(f"[FAIL] {result['hostname']} ({result['ip']})")
            for finding in result["findings"]:
                print(f"       {finding}")

    if args.report_file:
        report_path = Path(args.report_file).resolve()
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(results, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Report: {report_path}")
        except OSError as exc:
            print(f"Report write failed: {exc}", file=sys.stderr)
            return 2

    print(f"Summary: {len(results) - failed} compliant, {failed} non-compliant")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

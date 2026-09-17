from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.inventory import Inventory
from engine.ssh import SSHClient, SSHCommandError
from security.apply import apply_sshd_settings, validate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a validated SSH plan as one transaction per host.")
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--inventory", default=str(ROOT / "config" / "servers.test.txt"))
    parser.add_argument("--user", default="D25950")
    parser.add_argument("--key-file")
    parser.add_argument("--password-env", default="SM_AUTOMATION_SSH_PASSWORD")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--report-file", default=str(ROOT / "reports" / "security-apply.json"))
    parser.add_argument("--apply", action="store_true", help="Perform remote changes; default is dry run.")
    args = parser.parse_args()
    try:
        servers = Inventory().load(args.inventory)
        plan = validate_plan(json.loads(Path(args.plan_file).read_text(encoding="utf-8")), servers)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    total_actions = sum(len(record["actions"]) for record in plan)
    if not args.apply:
        print(f"Dry run: {total_actions} action(s) planned; no server changes made.")
        for record in plan:
            for action in record["actions"]:
                print(f"[{record['hostname']} {record['ip']}] {action['parameter']}: "
                      f"{action['current']} -> {action['recommended']}")
        return 0

    password = os.environ.get(args.password_env)
    if args.key_file and password:
        parser.error("Use --key-file or --password-env, not both.")
    if not args.key_file and not password:
        parser.error(f"Set {args.password_env} or provide --key-file for --apply.")

    # Check that the destination can be opened before any remote mutation.
    report_path = Path(args.report_file).resolve()
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("[]\n", encoding="utf-8")
    except OSError as exc:
        print(f"Report write failed: {exc}", file=sys.stderr)
        return 2

    passed = failed = 0
    results = []
    for record in plan:
        actions = record["actions"]
        if not actions:
            continue
        client = SSHClient(record["hostname"], record["ip"], user=args.user,
                           password=password, key_filename=args.key_file, timeout=args.timeout)
        result = {"hostname": record["hostname"], "ip": record["ip"], "action_count": len(actions)}
        try:
            output = apply_sshd_settings(client, actions).strip()
            passed += len(actions)
            result.update(status="passed", output=output)
            print(f"[PASS] {record['hostname']}: {len(actions)} action(s), reconnect verified")
            print(output)
        except (paramiko.SSHException, SSHCommandError, OSError, ValueError) as exc:
            failed += len(actions)
            result.update(status="failed", error=str(exc))
            print(f"[FAIL] {record['hostname']}: {exc}")
        finally:
            client.close()
        results.append(result)
        try:
            report_path.write_text(json.dumps(results, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Report write failed; stopping further changes: {exc}", file=sys.stderr)
            return 2

    print(f"Summary: {passed} action(s) passed, {failed} failed")
    print(f"Report: {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

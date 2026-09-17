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

from core.inventory import Inventory, InventoryError
from engine.ssh import SSHClient, SSHCommandError
from security.apply import apply_sshd_setting


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply an approved SSH remediation plan with backup and validation."
    )
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--inventory", default=str(ROOT / "config" / "servers.test.txt"))
    parser.add_argument("--user", default="D25950")
    parser.add_argument("--key-file")
    parser.add_argument("--password-env", default="SM_AUTOMATION_SSH_PASSWORD")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform remote changes; without this flag only show the plan.",
    )
    args = parser.parse_args()

    try:
        plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
        servers = Inventory().load(args.inventory)
        if not isinstance(plan, list):
            raise ValueError("Plan file must contain a list.")
    except (OSError, UnicodeError, ValueError, InventoryError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    actions_by_host = {
        record.get("hostname"): record.get("actions", [])
        for record in plan
        if isinstance(record, dict)
    }
    total_actions = sum(
        len(actions) for actions in actions_by_host.values() if isinstance(actions, list)
    )
    if not args.apply:
        print(f"Dry run: {total_actions} action(s) planned; no server changes made.")
        for hostname, actions in actions_by_host.items():
            for action in actions:
                print(
                    f"[{hostname}] {action['parameter']}: "
                    f"{action['current']} -> {action['recommended']}"
                )
        return 0

    password = os.environ.get(args.password_env)
    if args.key_file and password:
        parser.error("Use --key-file or --password-env, not both.")
    if not args.key_file and not password:
        parser.error(f"Set {args.password_env} or provide --key-file for --apply.")

    server_map = {server.hostname: server for server in servers}
    failed = 0
    for hostname, actions in actions_by_host.items():
        if not actions:
            continue
        server = server_map.get(hostname)
        if server is None:
            print(f"[FAIL] {hostname}: server is not in inventory")
            failed += 1
            continue
        client = SSHClient(
            server.hostname,
            server.ip,
            user=args.user,
            password=password,
            key_filename=args.key_file,
            timeout=args.timeout,
        )
        try:
            for action in actions:
                output = apply_sshd_setting(
                    client,
                    action["parameter"],
                    action["recommended"],
                ).strip()
                print(f"[PASS] {hostname}: {action['parameter']} applied")
                if output:
                    print(f"       {output}")
        except (paramiko.SSHException, SSHCommandError, OSError, ValueError, KeyError) as exc:
            failed += 1
            print(f"[FAIL] {hostname}: {exc}")
        finally:
            client.close()

    print(f"Summary: {total_actions - failed} action(s) passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

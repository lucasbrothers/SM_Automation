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
from security.audit import audit_linux_server


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a read-only Linux security baseline audit for the inventory."
    )
    parser.add_argument(
        "--inventory",
        default=str(ROOT / "config" / "servers.test.txt"),
        help="Inventory CSV path",
    )
    parser.add_argument("--user", default="D25950", help="SSH login user")
    parser.add_argument("--key-file", help="SSH private key path")
    parser.add_argument(
        "--password-env",
        default="SM_AUTOMATION_SSH_PASSWORD",
        help="Environment variable containing the SSH password",
    )
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds")
    parser.add_argument("--report-file", help="Optional JSON report path")
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if not args.key_file and not password:
        parser.error(f"Provide --key-file or set {args.password_env}.")
    if args.key_file and password:
        parser.error("Use --key-file or --password-env, not both.")

    try:
        servers = Inventory().load(args.inventory)
    except InventoryError as exc:
        print(f"Inventory validation failed: {exc}", file=sys.stderr)
        return 2

    results: list[dict[str, object]] = []
    failed = 0
    for server in servers:
        client = SSHClient(
            server.hostname,
            server.ip,
            user=args.user,
            password=password,
            key_filename=args.key_file,
            timeout=args.timeout,
        )
        try:
            audit = audit_linux_server(client)
            result = {
                "hostname": server.hostname,
                "ip": server.ip,
                "status": "passed",
                "root_accounts": list(audit.root_accounts),
                "sshd_settings": audit.sshd_settings,
                "sshd_config_mode": audit.sshd_config_mode,
            }
            results.append(result)
            print(f"[PASS] {server.hostname} ({server.ip})")
            print(f"       root accounts: {', '.join(audit.root_accounts)}")
            print(f"       sshd config: {audit.sshd_config_mode}")
            for name, value in audit.sshd_settings.items():
                print(f"       {name}: {value}")
        except (paramiko.SSHException, SSHCommandError, OSError, ValueError) as exc:
            failed += 1
            results.append({
                "hostname": server.hostname,
                "ip": server.ip,
                "status": "failed",
                "error": str(exc),
            })
            print(f"[FAIL] {server.hostname} ({server.ip}): {exc}")
        finally:
            client.close()

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

    print(f"Summary: {len(servers) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check SSH access and collect identity/system information for every inventory server."
    )
    parser.add_argument(
        "--inventory",
        default=str(ROOT / "config" / "servers.test.txt"),
        help="Inventory CSV path (default: config/servers.test.txt)",
    )
    parser.add_argument("--user", default="D25950", help="SSH login user")
    parser.add_argument("--key-file", help="SSH private key path")
    parser.add_argument(
        "--password-env",
        default="SM_AUTOMATION_SSH_PASSWORD",
        help="Environment variable containing the SSH password",
    )
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds")
    parser.add_argument(
        "--check-root",
        action="store_true",
        help="Verify root escalation with sudo su -c id for each server",
    )
    parser.add_argument(
        "--report-file",
        help="Optional JSON report path for the collected server results",
    )
    args = parser.parse_args()

    if args.key_file and os.environ.get(args.password_env):
        parser.error("Use --key-file or --password-env, not both.")

    password = os.environ.get(args.password_env)
    if not args.key_file and not password:
        parser.error(
            f"Provide --key-file or set the {args.password_env} environment variable."
        )

    try:
        servers = Inventory().load(args.inventory)
    except InventoryError as exc:
        print(f"Inventory validation failed: {exc}", file=sys.stderr)
        return 2

    failed = 0
    report: list[dict[str, object]] = []
    print(f"Inventory: {args.inventory}")
    print(f"Servers: {len(servers)}")
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
            identity = client.execute("id").strip()
            hostname = client.execute("hostname").strip()
            system = client.execute("uname -srm").strip()
            result: dict[str, object] = {
                "hostname": server.hostname,
                "ip": server.ip,
                "os": server.os,
                "status": "passed",
                "identity": identity,
                "remote_hostname": hostname,
                "system": system,
            }
            print(f"[PASS] {server.hostname} ({server.ip})")
            print(f"       id: {identity}")
            print(f"       hostname: {hostname}")
            print(f"       system: {system}")
            if args.check_root:
                root_identity = client.execute("sudo su -c id").strip()
                if "uid=0(" not in root_identity:
                    raise SSHCommandError(
                        f"Root escalation did not return uid=0: {root_identity}"
                    )
                result["root_identity"] = root_identity
                print(f"       root: {root_identity}")
            report.append(result)
        except (paramiko.SSHException, SSHCommandError, OSError, ValueError) as exc:
            failed += 1
            report.append({
                "hostname": server.hostname,
                "ip": server.ip,
                "os": server.os,
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
                json.dumps(report, ensure_ascii=True, indent=2) + "\n",
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
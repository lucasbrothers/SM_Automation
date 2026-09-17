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
from monitoring.collector import collect_linux_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect read-only Linux monitoring data for inventory servers."
    )
    parser.add_argument("--inventory", default=str(ROOT / "config" / "servers.test.txt"))
    parser.add_argument("--user", default="D25950")
    parser.add_argument("--key-file")
    parser.add_argument("--password-env", default="SM_AUTOMATION_SSH_PASSWORD")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--report-file", required=True)
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if args.key_file and password:
        parser.error("Use --key-file or --password-env, not both.")
    if not args.key_file and not password:
        parser.error(f"Set {args.password_env} or provide --key-file.")

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
            snapshot = collect_linux_snapshot(client)
            results.append({
                "hostname": server.hostname,
                "ip": server.ip,
                "status": "passed",
                "metrics": snapshot.to_dict(),
            })
            print(f"[PASS] {server.hostname} ({server.ip})")
            print(f"       uptime: {snapshot.uptime}")
            print(f"       load: {snapshot.load_average}")
            print(f"       memory_mb: {snapshot.memory_mb}")
            print(f"       root_fs: {snapshot.root_filesystem}")
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

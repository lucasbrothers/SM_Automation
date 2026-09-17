from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.inventory import Inventory, InventoryError
from engine.ssh import SSHCommandError, SSHKeyDistributor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy one SSH public key to every server in an inventory."
    )
    parser.add_argument(
        "--inventory",
        default=str(ROOT / "config" / "servers.test.txt"),
        help="Inventory CSV path (default: config/servers.test.txt)",
    )
    parser.add_argument(
        "--public-key-file",
        default=str(Path.home() / ".ssh" / "id_rsa.pub"),
        help="Local public key file",
    )
    parser.add_argument("--user", default="D25950", help="SSH login user")
    parser.add_argument("--key-file", help="Private key used to connect")
    parser.add_argument(
        "--password-env",
        default="SM_AUTOMATION_SSH_PASSWORD",
        help="Environment variable containing the SSH password",
    )
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds")
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if args.key_file and password:
        parser.error("Use --key-file or --password-env, not both.")
    if not args.key_file and not password:
        try:
            password = getpass.getpass("SSH password for the target account: ")
        except (EOFError, KeyboardInterrupt):
            print("\nPassword input cancelled.", file=sys.stderr)
            return 2
        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            return 2

    try:
        public_key = Path(args.public_key_file).read_text(encoding="utf-8").strip()
        servers = Inventory().load(args.inventory)
    except (OSError, UnicodeError) as exc:
        print(f"Input file error: {exc}", file=sys.stderr)
        return 2
    except InventoryError as exc:
        print(f"Inventory validation failed: {exc}", file=sys.stderr)
        return 2

    print(f"Inventory: {args.inventory}")
    print(f"Public key: {args.public_key_file}")
    print(f"Servers: {len(servers)}")

    failed = 0
    for server in servers:
        distributor = SSHKeyDistributor(
            server.hostname,
            server.ip,
            user=args.user,
            password=password,
            key_filename=args.key_file,
            timeout=args.timeout,
        )
        try:
            output = distributor.distribute(public_key).strip()
            print(f"[PASS] {server.hostname} ({server.ip}): key installed or already present")
            if output:
                print(f"       remote: {output}")
        except (paramiko.SSHException, SSHCommandError, OSError, ValueError) as exc:
            failed += 1
            print(f"[FAIL] {server.hostname} ({server.ip}): {exc}")

    print(f"Summary: {len(servers) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

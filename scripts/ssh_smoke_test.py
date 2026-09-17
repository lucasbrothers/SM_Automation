from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engine.ssh import SSHClient


def main() -> int:
    parser = argparse.ArgumentParser(description="SSH smoke test against the designated test server.")
    parser.add_argument("--host", default="192.168.192.131", help="Target host IP or hostname")
    parser.add_argument("--user", default="D25950", help="SSH login user")
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds")
    parser.add_argument("--key-file", default=None, help="Optional path to the SSH private key file")
    parser.add_argument("--password", default=None, help="Optional SSH password; do not hardcode secrets in repo files")
    parser.add_argument("--sudo-command", default="sudo su -", help="Command used to switch to root")
    args = parser.parse_args()

    client = SSHClient(
        "TEST01",
        args.host,
        user=args.user,
        timeout=args.timeout,
        password=args.password,
        key_filename=args.key_file,
    )
    try:
        print("[1/3] Connecting to target host...")
        client.connect()
        print("[2/3] Running id command...")
        user_result = client.execute("id")
        print(user_result.strip())

        print("[3/3] Switching to root via sudo...")
        sudo_result = client.execute(args.sudo_command)
        print(sudo_result.strip() or "sudo switch command completed without output")
        return 0
    except Exception as exc:  # pragma: no cover - smoke test script
        print(f"SSH smoke test failed: {exc}", flush=True)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

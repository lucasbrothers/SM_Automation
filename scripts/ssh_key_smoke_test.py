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
    parser = argparse.ArgumentParser(description="Key-based SSH smoke test for the project test server.")
    parser.add_argument("--host", default="192.168.192.131", help="Target host IP or hostname")
    parser.add_argument("--user", default="D25950", help="SSH login user")
    parser.add_argument("--key-file", required=True, help="Private key file for the D25950 account")
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds")
    parser.add_argument("--sudo-command", default="sudo su -", help="Command used to switch to root")
    args = parser.parse_args()

    client = SSHClient(
        "TEST01",
        args.host,
        user=args.user,
        timeout=args.timeout,
        key_filename=args.key_file,
    )

    try:
        print("[1/3] Connecting to target host...")
        client.connect()

        print("[2/3] Running id as D25950...")
        user_result = client.execute("id")
        print(user_result.strip())

        print("[3/3] Switching to root via sudo su -...")
        sudo_result = client.execute(args.sudo_command)
        print(sudo_result.strip() or "sudo command completed without output")
        return 0
    except Exception as exc:  # pragma: no cover - smoke test script
        print(f"SSH key-based smoke test failed: {exc}", flush=True)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

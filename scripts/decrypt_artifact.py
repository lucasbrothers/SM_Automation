"""Explicit Linux-side plaintext export of one encrypted artifact."""
from pathlib import Path
import argparse
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.config import load_config
from storage.encrypted import EncryptedStore


def main():
    parser = argparse.ArgumentParser(description="Decrypt one artifact on the Linux server; never overwrite output")
    parser.add_argument("relative_path", help="Encrypted path relative to BACKUP or DATA")
    parser.add_argument("--area", choices=["backup", "data"], default="backup")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    root = config.backup_directory if args.area == "backup" else config.data_directory
    payload = EncryptedStore(root, config.key_file).read_bytes(args.relative_path)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    print(f"Plaintext export created: {args.output}. Protect or remove it after use.")


if __name__ == "__main__":
    main()

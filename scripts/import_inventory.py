"""Import a Linux-side CSV into the encrypted inventory without starting jobs."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.config import load_config
from server.service import inventory_csv, load_ssh_profiles, verify_inventory_profiles
from storage.encrypted import EncryptedStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--config")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Inventory storage runs on the Linux main server; use Import CSV in the Windows GUI")
    config = load_config(args.config)
    with args.csv_file.open(encoding="utf-8-sig", newline="") as handle:
        rows = inventory_csv(handle.read())
    verify_inventory_profiles(rows, load_ssh_profiles(config.ssh_profiles_file))
    store = EncryptedStore(config.data_directory, config.key_file)
    store.write_json("inventory.json.enc", rows)
    print(f"Imported {len(rows)} servers into encrypted Linux storage")


if __name__ == "__main__":
    main()

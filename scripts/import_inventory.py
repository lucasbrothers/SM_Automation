"""Import a Linux-side CSV into the encrypted inventory without starting jobs."""
from pathlib import Path
import argparse
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.config import load_config
from server.service import inventory_records
from storage.encrypted import EncryptedStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    with args.csv_file.open(encoding="utf-8-sig", newline="") as handle:
        rows = inventory_records(list(csv.DictReader(handle)))
    store = EncryptedStore(config.data_directory, config.key_file)
    store.write_json("inventory.json.enc", rows)
    print(f"Imported {len(rows)} servers into encrypted Linux storage")


if __name__ == "__main__":
    main()

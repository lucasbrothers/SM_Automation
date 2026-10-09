"""Check Linux CSV import only in disposable encrypted storage on local WSL."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cryptography.fernet import Fernet
from storage.encrypted import EncryptedStore


def main():
    if sys.platform != "linux" or os.geteuid() != 0 or "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():
        raise RuntimeError("This check requires the authorized local WSL root environment")
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="sm-inventory-check-", dir="/opt") as directory:
        root = Path(directory)
        key = root / "test.key"; key.write_bytes(Fernet.generate_key()); key.chmod(0o600)
        profiles = root / "profiles.json"
        profiles.write_text(json.dumps({"rhel-admin": {"user": "root"}})); profiles.chmod(0o600)
        config = json.loads((project / "config/app.json").read_text())
        config["storage"] = {"data_directory": str(root / "DATA"), "backup_directory": str(root / "BACKUP"), "key_file": str(key)}
        config["ssh"]["profiles_file"] = str(profiles)
        settings = root / "app.json"; settings.write_text(json.dumps(config))
        source = root / "servers.csv"
        source.write_text("\ufeff Hostname , IP , OS , Profile\nsynthetic-rhel,127.0.0.1,RHEL 9,rhel-admin\n", encoding="utf-8")
        command = [sys.executable, str(project / "scripts/import_inventory.py"), str(source), "--config", str(settings)]
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        store = EncryptedStore(root / "DATA", key)
        rows = store.read_json("inventory.json.enc")
        assert rows[0]["profile"] == "rhel-admin"
        encrypted = store.path("inventory.json.enc").read_bytes()
        assert b"synthetic-rhel" not in encrypted
        for contents in ("hostname,ip,os\nlab,invalid,Linux\n", "hostname,ip,os,profile\nlab,127.0.0.1,Linux,missing\n"):
            source.write_text(contents)
            result = subprocess.run(command, capture_output=True, text=True)
            assert result.returncode != 0
            assert store.path("inventory.json.enc").read_bytes() == encrypted
        print("PASS: Linux CSV normalization, configured profile and encrypted storage")
        print("PASS: invalid IP and missing profile preserve existing inventory; no target SSH performed")


if __name__ == "__main__":
    main()

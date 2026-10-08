"""Configure the explicitly authorized local WSL lab; never print secrets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def run(*args):
    subprocess.run(args, check=True)


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Run as root inside the authorized WSL Ubuntu instance")
    root = Path(__file__).resolve().parents[1]
    address = subprocess.check_output(["hostname", "-I"], text=True).split()[0]
    secret_dir = Path("/root/.config/sm-automation")
    if not (secret_dir / "master.key").exists():
        run(sys.executable, str(root / "scripts/provision_server.py"), "--server-name", "localhost",
            "--server-ip", address, "--server-ip", "127.0.0.1")
    ssh_dir = Path("/root/.ssh")
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key = ssh_dir / "sm_automation_wsl"
    if not key.exists():
        run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", "sm-automation-loopback-lab")
    public = key.with_suffix(".pub").read_text().strip()
    authorized = ssh_dir / "authorized_keys"
    existing = authorized.read_text() if authorized.exists() else ""
    if public not in existing:
        with authorized.open("a") as handle:
            handle.write('\nfrom="127.0.0.1",no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty ' + public + "\n")
    authorized.chmod(0o600)
    host_public = Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().split()
    known = ssh_dir / "known_hosts"
    line = f"127.0.0.1 {host_public[0]} {host_public[1]}"
    content = known.read_text() if known.exists() else ""
    if line not in content:
        with known.open("a") as handle:
            handle.write("\n" + line + "\n")
    known.chmod(0o600)
    config_file = root / "config/app.local.json"
    if not config_file.exists():
        config = json.loads((root / "config/app.json").read_text(encoding="utf-8-sig"))
        config["ssh"].update(user="root", key_file=str(key), privilege="direct", max_workers=2)
        config_file.write_text(json.dumps(config, indent=2))
        config_file.chmod(0o600)
    sys.path.insert(0, str(root / "src"))
    from common.config import load_config
    from storage.encrypted import EncryptedStore
    config = load_config(config_file)
    store = EncryptedStore(config.data_directory, config.key_file)
    if store.read_json("inventory.json.enc") is None:
        store.write_json("inventory.json.enc", [{"hostname": "wsl-ubuntu", "ip": "127.0.0.1", "os": "Ubuntu 26.04", "profile": "default"}])
    unit = (root / "deploy/sm-automation.service").read_text()
    unit = unit.replace("User=smops", "User=root").replace("Group=smops", "Group=root")
    Path("/etc/systemd/system/sm-automation.service").write_text(unit)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "ssh.socket")
    run("systemctl", "enable", "--now", "sm-automation.service")
    print(f"Linux service configured at {address}:7443; SSH test target is this WSL instance only")


if __name__ == "__main__":
    main()

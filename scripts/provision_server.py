"""Generate server secrets and TLS certificates without printing private values."""
from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def write_exclusive(path, data, private=True):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def main():
    parser = argparse.ArgumentParser(description="Provision secrets on the Linux main server")
    parser.add_argument("--secrets-dir", type=Path, default=Path.home() / ".config" / "sm-automation")
    parser.add_argument("--server-name", required=True, help="DNS name or IP used by Windows clients")
    parser.add_argument("--server-ip", action="append", default=[])
    args = parser.parse_args()
    root = args.secrets_dir.expanduser().resolve()
    project = Path(__file__).resolve().parents[1]
    if root.is_relative_to(project):
        parser.error("Secrets must be kept outside the project and Git checkout")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    names = ["master.key", "api.token", "ca.key", "ca.crt", "server.key", "server.crt"]
    if any((root / name).exists() for name in names):
        parser.error("Existing secrets found. Do not regenerate the data key; preserve the existing directory.")
    identities = []
    for value in [args.server_name, *args.server_ip]:
        try:
            identities.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            identities.append(x509.DNSName(value))
    current = datetime.now(timezone.utc)
    ca_key, server_key = ec.generate_private_key(ec.SECP384R1()), ec.generate_private_key(ec.SECP384R1())
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SM Automation Private CA")])
    ca = (x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(current - timedelta(minutes=5))
          .not_valid_after(current + timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA384()))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.server_name)])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(server_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(current - timedelta(minutes=5))
            .not_valid_after(current + timedelta(days=825))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectAlternativeName(identities), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
            .sign(ca_key, hashes.SHA384()))
    for name, key in [("ca.key", ca_key), ("server.key", server_key)]:
        write_exclusive(root / name, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
    write_exclusive(root / "ca.crt", ca.public_bytes(serialization.Encoding.PEM), False)
    write_exclusive(root / "server.crt", cert.public_bytes(serialization.Encoding.PEM), False)
    write_exclusive(root / "master.key", Fernet.generate_key())
    write_exclusive(root / "api.token", secrets.token_urlsafe(48).encode("ascii"))
    print(f"Provisioned server files in {root}")
    print("Give Windows operators ca.crt and the API token through your approved channel.")
    print("Keep master.key, server.key and ca.key on Linux; back up master.key separately.")
    print("Never regenerate master.key for existing DATA or BACKUP files.")


if __name__ == "__main__":
    main()

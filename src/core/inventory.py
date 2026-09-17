from __future__ import annotations

import csv
import ipaddress
from dataclasses import dataclass
from pathlib import Path


class InventoryError(ValueError):
    """Raised when a server inventory file cannot be loaded or validated."""


@dataclass(frozen=True)
class ServerRecord:
    """Represents one server entry read from the inventory file."""

    hostname: str
    ip: str
    os: str


class Inventory:
    """Load and validate the server inventory used by SSH and management tasks."""

    def load(self, path: str | Path) -> list[ServerRecord]:
        """Read hostname/IP/OS rows and return validated records."""
        file_path = Path(path)

        if not file_path.exists():
            raise InventoryError(f"Server inventory file not found: {file_path}")

        if not file_path.is_file():
            raise InventoryError(f"Server inventory path is not a file: {file_path}")

        try:
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise InventoryError("Inventory file header is missing.")

                required = {"hostname", "ip", "os"}
                if set(reader.fieldnames) != required:
                    raise InventoryError("Inventory file must contain hostname, ip, and os columns.")

                records: list[ServerRecord] = []
                seen: set[str] = set()
                for row_index, row in enumerate(reader, start=2):
                    if row is None:
                        continue

                    hostname = (row.get("hostname") or "").strip()
                    ip_value = (row.get("ip") or "").strip()
                    os_name = (row.get("os") or "").strip()

                    if not hostname or not ip_value or not os_name:
                        raise InventoryError(f"Incomplete server row at line {row_index}.")

                    try:
                        ipaddress.ip_address(ip_value)
                    except ValueError as exc:
                        raise InventoryError(f"Invalid IP address at line {row_index}: {ip_value}") from exc

                    key = (hostname, ip_value)
                    if key in seen:
                        raise InventoryError(f"Duplicate server record: {hostname} {ip_value}")
                    seen.add(key)

                    records.append(ServerRecord(hostname=hostname, ip=ip_value, os=os_name))

                return records
        except OSError as exc:
            raise InventoryError(f"Unable to read server inventory: {file_path}") from exc

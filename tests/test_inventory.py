from __future__ import annotations

from pathlib import Path

import pytest

from core.inventory import Inventory, InventoryError


def test_inventory_loads_valid_server_rows(tmp_path):
    server_file = tmp_path / "servers.txt"
    server_file.write_text(
        "hostname,ip,os\n"
        "WEB01,10.10.10.1,Linux\n"
        "DB01,10.10.10.2,AIX\n",
        encoding="utf-8",
    )

    inventory = Inventory()
    servers = inventory.load(server_file)

    assert [server.hostname for server in servers] == ["WEB01", "DB01"]
    assert [server.ip for server in servers] == ["10.10.10.1", "10.10.10.2"]
    assert [server.os for server in servers] == ["Linux", "AIX"]


def test_inventory_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.txt"
    inventory = Inventory()

    with pytest.raises(InventoryError, match="missing"):
        inventory.load(missing)


def test_inventory_rejects_invalid_ip(tmp_path):
    server_file = tmp_path / "servers.txt"
    server_file.write_text(
        "hostname,ip,os\n"
        "WEB01,999.999.999.999,Linux\n",
        encoding="utf-8",
    )

    inventory = Inventory()

    with pytest.raises(InventoryError, match="Invalid IP"):
        inventory.load(server_file)


def test_inventory_rejects_duplicate_entries(tmp_path):
    server_file = tmp_path / "servers.txt"
    server_file.write_text(
        "hostname,ip,os\n"
        "WEB01,10.10.10.1,Linux\n"
        "WEB01,10.10.10.1,Linux\n",
        encoding="utf-8",
    )

    inventory = Inventory()

    with pytest.raises(InventoryError, match="Duplicate"):
        inventory.load(server_file)


def test_same_hostname_with_different_ip_is_rejected(tmp_path):
    path = tmp_path / "servers.csv"
    path.write_text("hostname,ip,os\nWEB01,192.0.2.1,Linux\nweb01,192.0.2.2,Linux\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="Duplicate"):
        Inventory().load(path)

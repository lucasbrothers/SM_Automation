import pytest
from server.service import inventory_csv


def test_excel_header_variations_and_optional_profile():
    rows = inventory_csv("\ufeff Hostname , IP , OS \r\nlab,127.0.0.1,Red Hat Enterprise Linux 9\r\n")
    assert rows == [{"hostname": "lab", "ip": "127.0.0.1", "os": "Red Hat Enterprise Linux 9", "profile": "default"}]


@pytest.mark.parametrize("content, message", [
    ("hostname,ip\nlab,127.0.0.1", "requires"),
    ("hostname,ip,os, IP\nlab,127.0.0.1,Linux,127.0.0.2", "duplicate column"),
    ("hostname,ip,os\nlab,invalid,Linux", "row 2"),
    ("hostname,ip,os\nlab,127.0.0.1,Linux,extra", "row 2 has extra"),
    ("hostname,ip,os\n,127.0.0.1,Linux", "row 2 requires"),
    ("hostname,ip,os\nlab,127.0.0.1,Linux\nLAB,127.0.0.2,Linux", "unique"),
])
def test_invalid_inventory_csv_reports_actionable_error(content, message):
    with pytest.raises(ValueError, match=message):
        inventory_csv(content)

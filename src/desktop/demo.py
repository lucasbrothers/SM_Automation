"""Synthetic, non-operational data used only for the visual mockup."""
SERVERS = [
    {"hostname": "web-prod-01", "ip": "192.0.2.11", "os": "RHEL 9"},
    {"hostname": "app-prod-02", "ip": "192.0.2.21", "os": "Linux"},
    {"hostname": "core-aix-01", "ip": "192.0.2.31", "os": "AIX 7.1"},
    {"hostname": "win-app-01", "ip": "192.0.2.41", "os": "Windows 2022"},
]


def connection_rows():
    rows = []
    peers = [[("198.51.100.15", "443"), ("192.0.2.21", "8443")],
             [("198.51.100.25", "1521"), ("192.0.2.31", "9000")],
             [("203.0.113.18", "22")]]
    for server, endpoints in zip(SERVERS, peers):
        connections = [{"protocol": "tcp", "local": {"address": server["ip"], "port": "50324"},
                        "remote": {"address": address, "port": port}, "state": "ESTABLISHED", "process": ""}
                       for address, port in endpoints]
        rows.append({**server, "status": "completed", "result": {"connections": connections}})
    return rows

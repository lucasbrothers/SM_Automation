"""Parse established TCP connections from Linux, AIX and Windows netstat."""
from __future__ import annotations

from engine.remote import capture


def os_family(name: str) -> str:
    value = name.casefold()
    if "aix" in value:
        return "aix"
    if "win" in value:
        return "windows"
    if any(word in value for word in ("linux", "rhel", "redhat", "red hat", "rocky", "ubuntu", "centos", "suse", "debian")):
        return "linux"
    raise ValueError(f"Unsupported operating system: {name}")


def endpoint(value: str) -> dict:
    if value.startswith("[") and "]:" in value:
        host, port = value[1:].rsplit("]:", 1)
    elif ":" in value and "." in value and value.rsplit(".", 1)[-1].isdigit():
        host, port = value.rsplit(".", 1)
    elif ":" in value:
        host, port = value.rsplit(":", 1)
    elif "." in value:
        host, port = value.rsplit(".", 1)
    else:
        host, port = value, ""
    return {"address": host, "port": port}


def parse_netstat(text: str) -> list[dict]:
    connections = []
    for line in text.splitlines():
        fields = line.split()
        if not fields or not fields[0].casefold().startswith("tcp"):
            continue
        states = [index for index, field in enumerate(fields) if field.upper() == "ESTABLISHED"]
        if not states or states[0] < 3:
            continue
        state = states[0]
        connections.append({
            "protocol": fields[0].lower(),
            "local": endpoint(fields[state - 2]),
            "remote": endpoint(fields[state - 1]),
            "state": "ESTABLISHED",
            "process": " ".join(fields[state + 1:]),
        })
    return connections


def collect_connections(client, family: str, timeout: int) -> dict:
    command = {"linux": "LC_ALL=C netstat -nt", "aix": "LC_ALL=C netstat -an -f inet; netstat -an -f inet6",
               "windows": "netstat -ano"}[family]
    result = capture(client, command, timeout=timeout, max_bytes=8 * 1024 * 1024)
    if result.exit_code != 0:
        raise RuntimeError("netstat failed: " + result.stderr[:500])
    return {"connections": parse_netstat(result.stdout.decode("utf-8", errors="replace")),
            "warning": result.stderr.strip()}

from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.ssh import SSHClient


@dataclass(frozen=True)
class MonitoringSnapshot:
    """Store read-only Linux resource observations."""

    uptime: str
    load_average: tuple[float, float, float]
    memory_mb: dict[str, int]
    root_filesystem: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_load(load_output: str) -> tuple[float, float, float]:
    values = load_output.strip().split()
    if len(values) < 3:
        raise ValueError("Invalid /proc/loadavg output")
    try:
        return tuple(float(value) for value in values[:3])  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError("Invalid load average value") from exc


def _parse_memory(memory_output: str) -> dict[str, int]:
    for line in memory_output.splitlines():
        fields = line.split()
        if fields and fields[0] == "Mem:" and len(fields) >= 7:
            try:
                return {
                    "total": int(fields[1]),
                    "used": int(fields[2]),
                    "free": int(fields[3]),
                    "shared": int(fields[4]),
                    "cache": int(fields[5]),
                    "available": int(fields[6]),
                }
            except ValueError as exc:
                raise ValueError("Invalid memory value") from exc
    raise ValueError("Mem line not found")


def _parse_filesystem(filesystem_output: str) -> dict[str, str]:
    lines = [line.split() for line in filesystem_output.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines[-1]) < 6:
        raise ValueError("Invalid filesystem output")
    fields = lines[-1]
    return {
        "filesystem": fields[0],
        "used": fields[2],
        "available": fields[3],
        "capacity": fields[4],
        "mounted_on": fields[5],
    }


def collect_linux_snapshot(client: SSHClient) -> MonitoringSnapshot:
    """Collect Linux resource metrics through an existing SSH client."""
    return MonitoringSnapshot(
        uptime=client.execute("uptime -p").strip(),
        load_average=_parse_load(client.execute("cat /proc/loadavg")),
        memory_mb=_parse_memory(client.execute("free -m")),
        root_filesystem=_parse_filesystem(client.execute("df -P /")),
    )

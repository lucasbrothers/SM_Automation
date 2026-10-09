"""Read-only RPM/DNF update discovery using existing repository cache."""
import re

from engine.remote import capture, privileged


def parse_updates(output, installed_output):
    installed = {}
    for line in installed_output.splitlines():
        fields = line.split("\t")
        if len(fields) == 3:
            name, version, architecture = fields
            installed.setdefault((name, architecture), []).append(version.removeprefix("0:"))
    packages = []
    seen = set()
    for line in output.splitlines():
        if line.strip().startswith("Obsoleting Packages"):
            break
        fields = line.split()
        if len(fields) != 3 or "." not in fields[0]:
            continue
        name, architecture = fields[0].rsplit(".", 1)
        version, repository = fields[1:]
        identity = name, architecture
        if identity not in installed or identity in seen:
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.-]*", name) or not re.fullmatch(r"[A-Za-z0-9.+:~_-]+", version):
            continue
        seen.add(identity)
        packages.append({"name": name, "architecture": architecture,
                         "installed": ", ".join(installed[identity]), "candidate": version,
                         "repository": repository})
    return packages


def list_updates(client, mode):
    query = "export LC_ALL=C; rpm -qa --qf '%{NAME}\\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\\t%{ARCH}\\n'"
    installed = capture(client, privileged(query, mode), timeout=180, max_bytes=4 * 1024 * 1024)
    if installed.exit_code:
        raise RuntimeError(installed.stderr.strip() or "RPM inventory query failed")
    response = capture(client, privileged("export LC_ALL=C; dnf -q --noplugins --cacheonly check-update", mode), timeout=180, max_bytes=4 * 1024 * 1024)
    if response.exit_code not in {0, 100}:
        raise RuntimeError(response.stderr.strip() or "DNF cache query failed; repository metadata must be prepared on the target")
    output = response.stdout.decode("utf-8", errors="replace")
    packages = parse_updates(output, installed.stdout.decode("utf-8", errors="replace"))
    if response.exit_code == 100 and not packages:
        raise ValueError("DNF reported updates but no installed update rows could be read")
    return {"action": "list", "manager": "dnf", "packages": packages, "output": output,
            "warnings": response.stderr, "note": "Existing cache only; RPM plan/apply is not supported. No refresh, install or reboot"}

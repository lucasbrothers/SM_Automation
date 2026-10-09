"""Linux patch discovery and version-pinned plans for apt and RPM/DNF."""
from __future__ import annotations

import re
import shlex

from engine.remote import capture, privileged


def validate_options(options):
    if not isinstance(options, dict) or options.get("action", "list") not in {"list", "plan", "apply"}:
        raise ValueError("Unknown patch action")
    action = options.get("action", "list")
    result = {"action": action}
    if action == "plan":
        packages = options.get("packages")
        if not isinstance(packages, list) or not 1 <= len(packages) <= 50:
            raise ValueError("Select between 1 and 50 installed packages")
        if any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._-]*(?::[A-Za-z0-9_]+)?(?:=[A-Za-z0-9.+:~_-]+)?", p) for p in packages):
            raise ValueError("Use package names, optionally followed by =version")
        result["packages"] = list(dict.fromkeys(packages))
    elif action == "apply":
        plan_id = options.get("plan_id", "")
        if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
            raise ValueError("Apply requires a completed patch plan ID")
        result["plan_id"] = plan_id
    return result


def execute(client, command, mode, timeout=180):
    command = "set -eu; export LC_ALL=C; command -v apt-get >/dev/null || { echo 'Only Debian/Ubuntu apt targets supported' >&2; exit 1; }; " + command
    result = capture(client, privileged(command, mode), timeout=timeout, max_bytes=4 * 1024 * 1024)
    if result.exit_code:
        raise RuntimeError(result.stderr.strip() or f"Package command exited {result.exit_code}")
    return result.stdout.decode("utf-8", errors="replace")


MANAGER_COMMAND = (
    "if test -f /etc/debian_version; then "
    "command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1 && echo apt || echo unsupported; "
    "elif test -f /etc/redhat-release; then "
    "command -v dnf >/dev/null 2>&1 && command -v rpm >/dev/null 2>&1 && echo dnf || echo unsupported; "
    "elif command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then echo apt; "
    "elif command -v dnf >/dev/null 2>&1 && command -v rpm >/dev/null 2>&1; then echo dnf; else echo unsupported; fi"
)


def package_manager(client):
    manager = client.execute(MANAGER_COMMAND).strip()
    if manager not in {"apt", "dnf"}:
        raise ValueError("No supported native package manager is available")
    return manager


def list_updates(client, mode):
    manager = package_manager(client)
    if manager == "dnf":
        from patch.rpm import list_updates as rpm_updates
        return rpm_updates(client, mode)
    if manager != "apt":
        raise ValueError("Patch discovery requires apt or RPM/DNF")
    output = execute(client, "apt list --upgradable 2>/dev/null", mode)
    packages = []
    for line in output.splitlines():
        match = re.match(r"([^/]+)/\S+ (\S+) (\S+) \[upgradable from: (.+)\]", line)
        if match:
            name, candidate, architecture, installed = match.groups()
            packages.append({"name": name, "installed": installed, "candidate": candidate, "architecture": architecture})
    return {"action": "list", "manager": "apt", "packages": packages, "output": output, "note": "Uses existing apt metadata; no refresh, install or reboot"}


def install_command(pins, simulate=True):
    return "apt-get " + ("-s " if simulate else "-y ") + "--no-remove --only-upgrade -o Dpkg::Options::=--force-confold install " + " ".join(shlex.quote(p) for p in pins)


def simulate(client, pins, mode):
    output = execute(client, install_command(pins), mode)
    operations = []
    for line in output.splitlines():
        if line.startswith("Remv "):
            raise ValueError("Plan contains package removals")
        if line.startswith("Inst "):
            match = re.match(r"Inst (\S+)(?: \[([^]]+)\])? \((\S+)", line)
            if not match:
                raise ValueError("Cannot read apt simulation operation")
            name, installed, candidate = match.groups()
            operations.append({"name": name, "installed": installed or "(new dependency)", "candidate": candidate})
    return operations, output


def make_plan(client, packages, mode):
    if package_manager(client) == "dnf":
        from patch.rpm_plan import make_plan as rpm_plan
        return rpm_plan(client, packages, mode)
    pins, selected = [], []
    for spec in packages:
        name, _, requested = spec.partition("=")
        installed = execute(client, "dpkg-query -W -f='${Status}\t${Version}' " + shlex.quote(name), mode).split("\t")
        if len(installed) != 2 or installed[0] != "install ok installed":
            raise ValueError("Only already installed packages may be selected: " + name)
        policy = execute(client, "apt-cache policy " + shlex.quote(name), mode)
        match = re.search(r"^\s*Candidate:\s*(\S+)", policy, re.MULTILINE)
        version = requested or (match.group(1) if match else "")
        if not re.fullmatch(r"[A-Za-z0-9.+:~_-]+", version) or version == "(none)":
            raise ValueError("No package candidate: " + name)
        execute(client, "dpkg --compare-versions " + shlex.quote(version) + " ge " + shlex.quote(installed[1]) +
                " || { echo 'Package downgrades are not supported' >&2; exit 1; }", mode)
        pins.append(name + "=" + version)
        selected.append({"name": name, "installed": installed[1], "candidate": version})
    operations, output = simulate(client, pins, mode)
    return {"action": "plan", "manager": "apt", "pins": pins, "packages": selected, "operations": operations, "output": output}


def apply_plan(client, plan, mode):
    expected = plan.get("manager", "apt")
    if expected not in {"apt", "dnf"} or package_manager(client) != expected:
        raise ValueError("Package manager changed since planning; create a fresh plan")
    if expected == "dnf":
        from patch.rpm_plan import apply_plan as rpm_apply
        return rpm_apply(client, plan, mode)
    operations, _ = simulate(client, plan["pins"], mode)
    if operations != plan["operations"]:
        raise ValueError("Package state changed since planning; create a fresh plan")
    output = execute(client, "export DEBIAN_FRONTEND=noninteractive; " + install_command(plan["pins"], False), mode, timeout=900)
    reboot = execute(client, "if [ -f /var/run/reboot-required ]; then echo yes; else echo no; fi", mode).strip()
    return {"action": "apply", "pins": plan["pins"], "output": output, "reboot_required": reboot == "yes", "note": "No automatic reboot; existing configuration files retained"}

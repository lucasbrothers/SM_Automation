"""Bounded read-only SSH probes; no target agent or package installation."""
import json
import math
import re
import shlex
import uuid
from datetime import datetime, timezone
from engine.remote import capture, powershell

from shared.ci_schema import AUTO_FIELDS

LINUX_PROBES = {
    "actual_hostname": "hostname", "addresses": "hostname -I",
    "primary_ip": "dev=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i==\"dev\") print $(i+1)}'); [ -n \"$dev\" ] && ip -4 -o addr show dev \"$dev\" scope global | awk 'NR==1 {split($4,a,\"/\"); print a[1]}'",
    "os_release": "cat /etc/os-release", "kernel": "uname -r", "architecture": "uname -m",
    "manufacturer": "cat /sys/class/dmi/id/sys_vendor", "hardware_model": "cat /sys/class/dmi/id/product_name",
    "serial_number": "cat /sys/class/dmi/id/product_serial", "hardware_uuid": "cat /sys/class/dmi/id/product_uuid",
    "virtualization": "systemd-detect-virt", "cpuinfo": "cat /proc/cpuinfo", "logical_cpus": "getconf _NPROCESSORS_ONLN",
    "smt_active": "cat /sys/devices/system/cpu/smt/active",
    "smt_control": "cat /sys/devices/system/cpu/smt/control",
    "affinity_cpus": "nproc", "lscpu": "LC_ALL=C lscpu -p=CORE,SOCKET", "meminfo": "cat /proc/meminfo",
    "uptime": "cat /proc/uptime", "boot_time": "awk '$1==\"btime\" {print $2}' /proc/stat",
    "cgroup": "cat /proc/self/cgroup",
    "gpu": "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=name,uuid,memory.total --format=csv,noheader,nounits; elif command -v lspci >/dev/null 2>&1; then lspci | grep -Ei 'VGA|3D controller|Display controller'; else printf 'UNKNOWN: GPU discovery tool unavailable'; fi",
}


def probe_script(probes, marker):
    return "\n".join("printf '\\n%s:%s\\n' " + shlex.quote(marker) + " " + shlex.quote(key) + "\n(" + command + ") 2>/dev/null\n:" for key, command in probes.items())


def parse_sections(text, marker):
    parts = re.split(r"(?:^|\n)" + re.escape(marker) + r":([a-z_]+)\r?\n", text)
    return {parts[i]: parts[i+1].strip() for i in range(1, len(parts)-1, 2)}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_linux(raw):
    row = {k: raw.get(k, "") for k in AUTO_FIELDS if k in raw}
    release = {}
    for line in raw.get("os_release", "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            try:
                release[key] = " ".join(shlex.split(value))
            except ValueError:
                pass
    row.update(os_name=release.get("NAME", "Linux"), os_version=release.get("VERSION_ID", release.get("VERSION", "")))
    row["primary_ip"] = row.get("primary_ip") or raw.get("addresses", "").split(" ")[0]
    models = re.findall(r"^(?:model name|Hardware|Processor)\s*:\s*(.+)$", raw.get("cpuinfo", ""), re.M)
    row["cpu_model"] = "; ".join(dict.fromkeys(models))
    visible = number(raw.get("logical_cpus"))
    affinity = number(raw.get("affinity_cpus"))
    limits = [n for n in [visible, affinity] if n and n > 0]
    for line in raw.get("cpu_limit", "").splitlines():
        quota = line.split()
        if len(quota) == 2 and number(quota[0]) is not None and number(quota[1]):
            limits.append(float(quota[0]) / float(quota[1]))
    row["logical_cpus"] = int(visible) if visible else None
    row["allocated_cpus"] = round(min(limits), 3) if limits else None
    cores = {line for line in raw.get("lscpu", "").splitlines() if line and not line.startswith("#")}
    row["physical_cores"] = len(cores) or None
    active = raw.get("smt_active", "").strip()
    control = raw.get("smt_control", "").strip()
    if active in {"0", "1"}:
        row["smt_enabled"] = "켜짐" if active == "1" else "꺼짐"
        row["smt_details"] = "Linux kernel smt/active="+active+"; control="+(control or "미확인")
    else:
        topology = [line.strip() for line in raw.get("lscpu", "").splitlines() if re.fullmatch(r"\d+,\d+", line.strip())]
        if len(topology) > len(set(topology)):
            row["smt_enabled"] = "켜짐"
            row["smt_details"] = "OS가 같은 socket/core에 여러 논리 CPU를 보고함"
        else:
            row["smt_enabled"] = "확인 불가"
            row["smt_details"] = "kernel SMT 상태 미제공. 논리 CPU/core 수만으로 꺼짐을 단정하지 않음"
    if raw.get("virtualization") not in {None, "", "none"}:
        row["smt_details"] += "; 가상 환경에 노출된 상태이며 물리 HOST SMT 상태는 별도 확인"
    mem = re.search(r"^MemTotal:\s*(\d+)", raw.get("meminfo", ""), re.M)
    memory = int(mem[1])*1024 if mem else None
    memory_limits = [number(line) for line in raw.get("memory_limit", "").splitlines()]
    limit = min((n for n in memory_limits if n and n > 0), default=None)
    row["memory_gib"] = round(memory / 1024**3, 3) if memory else None
    row["allocated_memory_gib"] = round(min(memory, limit) / 1024**3, 3) if memory and limit and limit > 0 else row["memory_gib"]
    row["uptime_seconds"] = number(raw.get("uptime", "").split(" ")[0])
    boot = number(raw.get("boot_time"))
    if boot is not None:
        try: row["boot_time"] = datetime.fromtimestamp(boot, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError): row["boot_time"] = ""
    warnings = []
    for field in ("serial_number", "hardware_uuid", "cpu_model", "hardware_model", "primary_ip", "os_version", "allocated_cpus", "allocated_memory_gib", "uptime_seconds"):
        if not row.get(field):
            warnings.append(AUTO_FIELDS[field] + ": 확인 불가 / 권한 또는 플랫폼 제한")
    if not row.get("gpu") or row.get("gpu", "").startswith("UNKNOWN:"):
        row["gpu"] = "미확인"
        warnings.append("GPU: 탐지 결과 없음 또는 도구 미설치 (GPU 없음으로 단정하지 않음)")
    if raw.get("cgroup") and not raw.get("cpu_limit"):
        warnings.append("cgroup CPU 상한 미확인: OS/affinity 기준")
    row["warnings"] = "\n".join(warnings)
    return row


def parse_aix(raw):
    def field(name):
        found = re.search(r"^\s*"+re.escape(name)+r"\s*:\s*(.+)$", raw.get("prtconf", "")+"\n"+raw.get("lpar", ""), re.M)
        return found[1] if found else ""
    cpus = number(field("Online Virtual CPUs")) or number(field("Number Of Processors"))
    memory = number(field("Memory Size").split(" ")[0])
    ips = [ip for ip in raw.get("addresses", "").split() if not ip.startswith("127.")]
    up = raw.get("uptime", ""); uptime = None
    if " up " in up:
        tail = up.split(" up ", 1)[1].split("user", 1)[0]
        days = re.search(r"(\d+)\s+days?", tail)
        clock = re.search(r"(\d+):(\d+)", tail)
        hours = re.search(r"(\d+)\s+hrs?", tail)
        minutes = re.search(r"(\d+)\s+mins?", tail)
        if days or clock or hours or minutes:
            uptime = (int(days[1])*86400 if days else 0)+(int(clock[1])*3600+int(clock[2])*60 if clock else 0)+(int(hours[1])*3600 if hours else 0)+(int(minutes[1])*60 if minutes else 0)
    smt = raw.get("smt", "")
    match = re.search(r"SMT is (?:currently|now) (enabled|disabled)", smt, re.I)
    state = ("켜짐" if match[1].lower() == "enabled" else "꺼짐") if match else "확인 불가"
    return {
        "smt_enabled": state, "smt_details": (smt.strip()[:4000] or "smtctl 조회 결과 없음 / 권한 또는 플랫폼 제한") + "; LPAR에 보고된 상태 기준",
        "actual_hostname": raw.get("actual_hostname"), "primary_ip": raw.get("primary_ip") or (ips[0] if ips else ""),
        "addresses": " ".join(ips), "os_name": "AIX", "os_version": raw.get("os_version"),
        "architecture": raw.get("architecture"), "hardware_model": raw.get("hardware_model"),
        "serial_number": field("Machine Serial Number"), "cpu_model": field("Processor Type"),
        "logical_cpus": cpus, "allocated_cpus": cpus, "physical_cores": None,
        "memory_gib": round(memory/1024,3) if memory else None, "allocated_memory_gib": round(memory/1024,3) if memory else None,
        "gpu": raw.get("gpu") or "미확인", "boot_time": raw.get("boot_time"), "uptime_seconds": uptime,
        "warnings": "LPAR에 노출된 자원 기준. 물리 core/GPU 없음 여부는 별도 확인. CPU entitlement: "+field("Entitled Capacity")+"; 원본 uptime: "+up,
    }


def windows_smt(topology):
    """CIM reports guest-visible topology, not a physical HOST's firmware mode."""
    enabled = False; unknown = False
    if not isinstance(topology, list) or not topology:
        unknown = True; topology = []
    for cpu in topology:
        if not isinstance(cpu, dict): unknown = True; continue
        cores = number(cpu.get("enabled_cores")) or number(cpu.get("cores"))
        logical = number(cpu.get("logical"))
        if not cores or not logical or logical < cores:
            unknown = True
        elif logical > cores:
            enabled = True
    state = "켜짐" if enabled else "확인 불가" if unknown else "꺼짐"
    return {"smt_enabled": state, "smt_details": "Windows CIM 활성 core/논리 CPU 기준. VM에서는 노출된 상태이며 물리 HOST SMT 상태는 별도 확인"}


WINDOWS_SCRIPT = r'''
$ErrorActionPreference='Stop'
$c=Get-CimInstance Win32_ComputerSystem; $o=Get-CimInstance Win32_OperatingSystem
$b=Get-CimInstance Win32_BIOS; $p=Get-CimInstance Win32_ComputerSystemProduct
$cpu=@(Get-CimInstance Win32_Processor); $net=@(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True')
$default=@($net | Where-Object {$_.DefaultIPGateway})
$ips=@($net | ForEach-Object {$_.IPAddress} | Where-Object {$_ -match '^\d+\.'})
$primary=@($default | ForEach-Object {$_.IPAddress} | Where-Object {$_ -match '^\d+\.'})
$topology=@($cpu | ForEach-Object {@{cores=$_.NumberOfCores; enabled_cores=$_.NumberOfEnabledCore; logical=$_.NumberOfLogicalProcessors}})
$gpu=@(Get-CimInstance Win32_VideoController | ForEach-Object {$_.Name})
@{cpu_topology=$topology; actual_hostname=$c.Name; primary_ip=($primary | Select-Object -First 1); addresses=($ips -join ' ');
os_name=$o.Caption; os_version=($o.Version+' build '+$o.BuildNumber); kernel=$o.Version; architecture=$o.OSArchitecture;
manufacturer=$c.Manufacturer; hardware_model=$c.Model; serial_number=$b.SerialNumber; hardware_uuid=$p.UUID;
cpu_model=(($cpu | ForEach-Object {$_.Name} | Select-Object -Unique) -join '; ');
logical_cpus=$c.NumberOfLogicalProcessors; allocated_cpus=$c.NumberOfLogicalProcessors;
physical_cores=($cpu | Measure-Object NumberOfCores -Sum).Sum; memory_gib=[math]::Round($c.TotalPhysicalMemory/1GB,3);
allocated_memory_gib=[math]::Round($c.TotalPhysicalMemory/1GB,3); gpu=($gpu -join '; ');
uptime_seconds=[math]::Floor(((Get-Date)-$o.LastBootUpTime).TotalSeconds); boot_time=$o.LastBootUpTime.ToString('o');
warnings='VM에서는 guest에 노출된 하드웨어 기준. Windows job/container 제한은 별도 확인.'} | ConvertTo-Json -Compress
'''


def collect(client, family, login_password=""):
    if family == "windows":
        result = capture(client, powershell(WINDOWS_SCRIPT), timeout=90, max_bytes=1024*1024)
        if result.exit_code:
            raise ValueError("Windows CIM discovery failed: " + result.stderr[:500])
        row = json.loads(result.stdout.decode("utf-8-sig").strip())
        if not isinstance(row, dict) or not row.get("actual_hostname"):
            raise ValueError("Invalid Windows discovery response")
        row.update(windows_smt(row.get("cpu_topology")))
        return {k: row.get(k) for k in AUTO_FIELDS}
    marker = "SMCI" + uuid.uuid4().hex
    if family == "aix":
        probes = {
            "actual_hostname": "hostname", "addresses": "ifconfig -a | awk '$1==\"inet\" {print $2}'",
            "primary_ip": "dev=$(netstat -rn -f inet | awk '$1==\"default\" {print $NF;exit}'); [ -n \"$dev\" ] && ifconfig \"$dev\" | awk '$1==\"inet\" {print $2;exit}'",
            "os_version": "oslevel -s", "hardware_model": "uname -M", "architecture": "uname -p",
            "prtconf": "LC_ALL=C prtconf", "lpar": "LC_ALL=C lparstat -i", "smt": "LC_ALL=C smtctl", "gpu": "LC_ALL=C lsdev -Cc display",
            "uptime": "LC_ALL=C uptime", "boot_time": "LC_ALL=C who -b",
        }
    else:
        probes = LINUX_PROBES
    result = capture(client, "sh -c " + shlex.quote(probe_script(probes, marker)), timeout=90, max_bytes=1024*1024)
    if result.exit_code:
        raise ValueError("CI discovery failed: " + result.stderr[:500])
    raw = parse_sections(result.stdout.decode("utf-8", errors="replace"), marker)
    if not raw.get("actual_hostname"):
        raise ValueError("CI discovery did not return a hostname")
    if family == "aix":
        return parse_aix(raw)
    missing = [k for k in ("serial_number", "hardware_uuid") if not raw.get(k)]
    if missing:
        probes = {k: LINUX_PROBES[k] for k in missing}
        try:
            privileged = client.execute_root("sh -c " + shlex.quote(probe_script(probes, marker)), login_password=login_password)
            if privileged["exit_code"] == 0:
                raw.update(parse_sections(privileged["stdout"], marker))
        except Exception:
            pass  # Retain explicit unknowns when root access is unavailable.
    # Resolve the SSH process's own v2 cgroup, never assume host root limits.
    group = next((line[3:] for line in raw.get("cgroup", "").splitlines() if line.startswith("0::")), None)
    if group is not None and ".." not in group.split("/"):
        base = "/sys/fs/cgroup/" + group.lstrip("/")
        def ancestors(filename):
            return "p="+shlex.quote(base)+"; while :; do cat \"$p/"+filename+"\"; [ \"$p\" = /sys/fs/cgroup ] && break; p=${p%/*}; [ -n \"$p\" ] || break; done"
        limit_probes = {"cpu_limit": ancestors("cpu.max"), "memory_limit": ancestors("memory.max")}
        limits = capture(client, "sh -c " + shlex.quote(probe_script(limit_probes, marker)), timeout=30, max_bytes=16384)
        if not limits.exit_code:
            raw.update(parse_sections(limits.stdout.decode("utf-8", errors="replace"), marker))
    return parse_linux(raw)

"""Read-only OS backup profiles, executed only by the Linux main server."""
from __future__ import annotations

import shlex

from engine.remote import powershell

LINUX_PATHS = [
    "/etc/passwd", "/etc/group", "/etc/shadow", "/etc/gshadow", "/etc/sudoers", "/etc/sudoers.d",
    "/etc/ssh", "/etc/pam.d", "/etc/security", "/etc/login.defs", "/etc/fstab", "/etc/hosts",
    "/etc/resolv.conf", "/etc/nsswitch.conf", "/etc/sysctl.conf", "/etc/sysctl.d", "/etc/crontab",
    "/etc/cron.d", "/var/spool/cron", "/etc/systemd/system", "/etc/netplan", "/etc/network",
    "/etc/NetworkManager/system-connections", "/etc/chrony.conf", "/etc/ntp.conf", "/etc/audit",
    "/etc/rsyslog.conf", "/etc/rsyslog.d", "/etc/logrotate.conf", "/etc/logrotate.d",
    "/etc/redhat-release", "/etc/sysconfig", "/etc/selinux", "/etc/authselect",
    "/etc/crypto-policies", "/etc/firewalld", "/etc/yum.repos.d", "/etc/dnf", "/etc/yum.conf",
]
AIX_PATHS = [
    "/etc/passwd", "/etc/group", "/etc/security", "/etc/sudoers", "/etc/sudoers.d",
    "/opt/freeware/etc/sudoers", "/opt/freeware/etc/sudoers.d", "/etc/ssh", "/etc/hosts",
    "/etc/resolv.conf", "/etc/netsvc.conf", "/etc/filesystems", "/etc/inittab", "/etc/environment",
    "/etc/rc.net", "/etc/rc.tcpip", "/etc/inetd.conf", "/etc/ntp.conf", "/var/spool/cron/crontabs",
]


def unix_archive(paths: list[str]) -> str:
    lines = ["set --"]
    for path in paths:
        lines.append(f"if [ -e {shlex.quote(path)} ]; then set -- \"$@\" {shlex.quote(path.lstrip('/'))}; "
                     f"else printf '%s\\n' {shlex.quote('Missing optional path: ' + path)} >&2; fi")
    lines.extend(['[ "$#" -gt 0 ] || exit 2', 'cd / && tar -cf - "$@"'])
    return "\n".join(lines)


def account_commands(tool: str) -> str:
    body = ("chage -l \"$account\"" if tool == "chage" else "sudo -n -l -U \"$account\"")
    return ("export LC_ALL=C; failed=0; "
            "accounts=$(getent passwd 2>/dev/null || cat /etc/passwd); "
            "for account in $(printf '%s\\n' \"$accounts\" | cut -d: -f1); do "
            "printf '\\n===== %s =====\\n' \"$account\"; " + body +
            "; rc=$?; printf '\\nexit_code=%s\\n' \"$rc\"; [ \"$rc\" -eq 0 ] || failed=1; done; exit \"$failed\"")


def commands(family: str) -> dict[str, str]:
    if family == "linux":
        return {
            "system": "uname -a; cat /etc/os-release; uptime; hostname",
            "accounts": "getent passwd; getent group",
            "account_expiry_chage": account_commands("chage"),
            "account_sudo_privileges": account_commands("sudo"),
            "storage": "df -hPT; lsblk -f; mount; cat /proc/swaps",
            "network": "ip address; ip route; netstat -an",
            "services": "systemctl list-unit-files --no-pager; systemctl list-units --type=service --no-pager",
            "packages": "if [ -f /etc/debian_version ] && command -v dpkg-query >/dev/null; then dpkg-query -W; elif command -v rpm >/dev/null; then rpm -qa; elif command -v dpkg-query >/dev/null; then dpkg-query -W; else echo 'No supported package inventory tool' >&2; exit 1; fi",
            "kernel": "sysctl -a",
            "schedule": "export LC_ALL=C; failed=0; for account in $(cut -d: -f1 /etc/passwd); do printf '\\n===== %s =====\\n' \"$account\"; output=$(crontab -l -u \"$account\" 2>&1); rc=$?; printf '%s\\n' \"$output\"; if [ \"$rc\" -ne 0 ]; then case \"$output\" in *'no crontab for'*) :;; *) failed=1;; esac; fi; done; exit \"$failed\"",
        }
    if family == "aix":
        return {
            "system": "uname -a; oslevel -s; prtconf; uptime",
            "accounts": "lsuser -a ALL ALL; lsgroup ALL",
            "account_expiry": "lsuser -a maxage minage maxexpired expires pwdwarntime ALL",
            "account_sudo_privileges": account_commands("sudo"),
            "storage": "df -g; lsvg; lspv; mount",
            "network": "ifconfig -a; netstat -rn; netstat -an",
            "services": "lssrc -a",
            "packages": "lslpp -L; emgr -l",
            "kernel": "no -a; vmo -a; ioo -a; schedo -a",
        }
    scripts = {
        "system": "Get-ComputerInfo | Format-List; Get-CimInstance Win32_OperatingSystem | Format-List",
        "accounts": "Get-LocalUser | Format-List *; Get-LocalGroup | ForEach-Object { $_; Get-LocalGroupMember -Group $_.Name }",
        "account_expiry": "Get-LocalUser | ForEach-Object { net user $_.Name }",
        "network": "Get-NetIPConfiguration | Format-List; Get-NetRoute | Format-Table -AutoSize; netstat -ano",
        "services": "Get-Service | Format-Table -AutoSize; Get-ScheduledTask | Format-List",
        "storage": "Get-Disk | Format-List; Get-Volume | Format-List",
        "patches": "Get-HotFix | Format-Table -AutoSize",
        "firewall": "Get-NetFirewallProfile | Format-List; Get-NetFirewallRule | Format-List",
        "audit_policy": "auditpol.exe /get /category:*",
        "local_policy": "net accounts; reg.exe query HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies /s",
    }
    return {name: powershell("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); " + script) for name, script in scripts.items()}


def windows_files() -> str:
    """Capture configuration files as JSON/base64 without remote temp files."""
    return powershell(r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$paths=@('C:\ProgramData\ssh','C:\Windows\System32\drivers\etc\hosts',
 'C:\Windows\System32\GroupPolicy','C:\Windows\System32\Tasks')
$items=@(); $errors=@(); $total=0
foreach($path in $paths) {
 if(-not (Test-Path -LiteralPath $path)) { $errors += "Missing optional path: $path"; continue }
 try {
  foreach($file in (Get-ChildItem -LiteralPath $path -File -Recurse -ErrorAction Stop)) {
   try {
    $total += $file.Length
    if($total -gt 32MB) { throw 'Windows file capture exceeded 32 MiB' }
    $items += @{path=$file.FullName; content=[Convert]::ToBase64String([IO.File]::ReadAllBytes($file.FullName))}
   } catch { $errors += $_.Exception.Message }
  }
 } catch { $errors += $_.Exception.Message }
}
@{format='base64-files-v1'; files=$items; warnings=$errors} | ConvertTo-Json -Depth 5 -Compress
if($errors.Count -gt 0) { exit 1 }
""")

"""Fixed, read-only Windows local account and installed KB queries."""
import json
import math
from engine.remote import capture, powershell, powershell_diagnostics

PREFIX = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
SCRIPTS = {
    "monitoring": PREFIX + r"""
$os=Get-CimInstance Win32_OperatingSystem
$cpu=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
$disk=Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='"+$os.SystemDrive+"'")
if($null -eq $cpu.PercentProcessorTime -or $null -eq $disk.Size -or $null -eq $disk.FreeSpace -or $null -eq $os.TotalVisibleMemorySize -or $null -eq $os.FreePhysicalMemory){throw 'Missing Windows resource counters'}
@{cpu_percent=[double]$cpu.PercentProcessorTime;total_kib=[double]$os.TotalVisibleMemorySize;free_kib=[double]$os.FreePhysicalMemory;disk_size=[double]$disk.Size;disk_free=[double]$disk.FreeSpace;system_drive=[string]$os.SystemDrive;uptime_seconds=[math]::Floor(($os.LocalDateTime-$os.LastBootUpTime).TotalSeconds)} | ConvertTo-Json -Compress
""",
    "accounts": PREFIX + r"""
$warnings=@();$groups=@{};$profiles=@{}
try { Get-CimInstance Win32_UserProfile | ForEach-Object { $profiles[[string]$_.SID]=[string]$_.LocalPath } } catch { $warnings+='Profile paths unavailable' }
foreach($g in @(Get-LocalGroup)) {
 try { foreach($m in @(Get-LocalGroupMember -Group $g.Name)) { $sid=[string]$m.SID.Value;$groups[$sid]=@($groups[$sid])+@([string]$g.Name) } }
 catch { $warnings+=('Group membership unavailable: '+$g.Name) }
}
$accounts=@(Get-LocalUser | ForEach-Object {
 $sid=[string]$_.SID.Value
 @{username=[string]$_.Name;uid=$sid;gid=(@($groups[$sid]) -join ', ');comment=[string]$_.Description;home=[string]$profiles[$sid];shell='';full_name=[string]$_.FullName;enabled=[bool]$_.Enabled;account_expires=[string]$_.AccountExpires;password_expires=[string]$_.PasswordExpires;last_logon=[string]$_.LastLogon}
})
@{accounts=$accounts;warnings=@($warnings)} | ConvertTo-Json -Depth 5 -Compress
""",
    "patches": PREFIX + r"""
$packages=@(Get-HotFix | ForEach-Object {
 $date='';if($_.InstalledOn){$date=Get-Date $_.InstalledOn -Format 'yyyy-MM-dd'}
 @{name=[string]$_.HotFixID;installed=$date;candidate='Installed';description=[string]$_.Description;installed_by=[string]$_.InstalledBy}
})
@{packages=$packages;warnings=@()} | ConvertTo-Json -Depth 5 -Compress
""",
}

def query_script(kind, options):
    if kind not in SCRIPTS or options.get("action", "list") != "list":
        raise ValueError("Windows accounts and patches are read-only")
    return SCRIPTS[kind]

def parse_query(kind, data):
    if data.get("exit_code", 0) != 0:
        raise ValueError(powershell_diagnostics(data.get("stderr", "")) or "Windows query failed")
    payload=json.loads(data.get("stdout", "").lstrip("\ufeff"))
    if kind=="monitoring":return parse_resources(payload)
    key="accounts" if kind=="accounts" else "packages"
    if not isinstance(payload,dict) or not isinstance(payload.get(key),list) or any(not isinstance(r,dict) for r in payload[key]):
        raise ValueError("Invalid Windows query result")
    warnings=payload.get("warnings",[])
    if not isinstance(warnings,list):raise ValueError("Invalid Windows query warnings")
    note=("Windows 로컬 계정 조회 전용 (도메인 계정 제외)" if kind=="accounts" else
          "Windows 설치된 KB 조회 전용 (Get-HotFix/CBS). 미설치 업데이트·앱·드라이버 전체 목록은 포함하지 않습니다. 검색·설치·재부팅을 수행하지 않습니다.")
    return {"action":"list",key:payload[key],"manager":"windows-installed-kb" if kind=="patches" else "windows-local","note":note,"warnings":"; ".join(str(w) for w in warnings)}

def collect_query(client,kind,options):
    result=capture(client,powershell(query_script(kind,options)),timeout=90,max_bytes=2*1024*1024)
    return parse_query(kind,{"stdout":result.stdout.decode("utf-8-sig"),"stderr":result.stderr,"exit_code":result.exit_code})


def parse_resources(payload):
    if not isinstance(payload,dict):raise ValueError("Invalid Windows resource result")
    def number(key):
        value=payload.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError("Invalid Windows resource counter: "+key)
        return value
    cpu=number("cpu_percent");total=number("total_kib");free=number("free_kib")
    size=number("disk_size");disk_free=number("disk_free");seconds=number("uptime_seconds")
    drive=payload.get("system_drive","")
    if cpu>100 or total<=0 or free>total or size<=0 or disk_free>size or not isinstance(drive,str) or len(drive)!=2 or not drive[0].isalpha() or drive[1]!=":":
        raise ValueError("Invalid Windows resource ranges")
    hours,remainder=divmod(int(seconds),3600);minutes,secs=divmod(remainder,60)
    return {"cpu_percent":cpu,"load_average":[],"uptime_seconds":int(seconds),"uptime":f"{hours:,}시간 {minutes:02}분 {secs:02}초",
            "memory_mb":{"total":int(total/1024),"used":int((total-free)/1024),"free":int(free/1024)},
            "root_filesystem":{"filesystem":drive,"mounted_on":drive,"used":str(int(size-disk_free)),"available":str(int(disk_free)),"capacity":str(round(100*(size-disk_free)/size))+"%"},
            "warnings":"","note":"Windows CPU는 WMI _Total 사용률(%)이며 Linux/AIX Load와 다릅니다. 메모리는 OS 가시 물리 메모리-무료 메모리, 디스크는 Windows 시스템 드라이브입니다."}

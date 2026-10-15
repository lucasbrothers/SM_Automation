"""Read-only AIX adapters; native commands, no CLIENT Python dependency."""
import re
from engine.remote import capture

COMMANDS = {
    "accounts": "LC_ALL=C /usr/sbin/lsuser -f -a id pgrp groups gecos home shell account_locked expires ALL",
    "filesets": "LC_ALL=C /usr/bin/lslpp -lc",
    "oslevel": "LC_ALL=C /usr/bin/oslevel -s",
    "fixes": "LC_ALL=C /usr/sbin/emgr -l",
    "uptime": "LC_ALL=C /usr/bin/uptime",
    "memory": "LC_ALL=C /usr/bin/vmstat -v",
    "filesystem": "LC_ALL=C /usr/bin/df -Pk /",
}

def read(client,key):
    result=capture(client,COMMANDS[key],timeout=60,max_bytes=4*1024*1024)
    if result.exit_code:
        raise ValueError("AIX "+key+": "+(result.stderr.strip() or "query failed (exit %s)" % result.exit_code))
    return result.stdout.decode("utf-8",errors="replace")

def parse_accounts(output):
    rows=[];current=None
    for line in output.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            current={"username":line.strip()[:-1]};rows.append(current)
        elif line.strip():
            if current is None or "=" not in line:raise ValueError("Invalid AIX account stanza")
            name,value=line.strip().split("=",1);current[name.strip()]=value.strip()
    if not rows:raise ValueError("No AIX account stanzas returned")
    for row in rows:
        if not row.get("id", "").isdigit():raise ValueError("Missing AIX account id")
    return [{"username":r["username"],"uid":r["id"],"gid":r.get("pgrp",""),"groups":r.get("groups",""),
             "comment":r.get("gecos",""),"home":r.get("home",""),"shell":r.get("shell",""),
             "enabled": {"true":False,"false":True}.get(r.get("account_locked","")),
             "account_expires":r.get("expires","")} for r in rows]

def accounts(client,options):
    if options.get("action","list")!="list":raise ValueError("AIX account operations are read-only")
    return {"action":"list","accounts":parse_accounts(read(client,"accounts")),
            "note":"AIX lsuser 조회 전용. Enabled는 account_locked의 반대값이며 SSH 로그인 가능 여부 전체를 뜻하지 않습니다. Expires는 AIX 원본 형식(0=만료 없음)."}

def parse_filesets(output):
    rows=[];header=None
    for line in output.splitlines():
        if not line.strip():continue
        if line.startswith("#"):
            fields=[x.strip().lower() for x in line[1:].split(":")]
            if "fileset" in fields and "level" in fields:header=fields
            continue
        fields=line.split(":")
        if header is None or len(fields)<len(header):raise ValueError("Invalid AIX lslpp colon output")
        value=dict(zip(header,fields))
        if not value.get("fileset") or not value.get("level"):raise ValueError("Incomplete AIX fileset row")
        rows.append({"name":value["fileset"],"installed":value["level"],"candidate":value.get("state",""),
                     "description":value.get("description",""),"source":value.get("path",""),"type":"fileset"})
    if header is None:raise ValueError("Missing AIX fileset header")
    return rows

def parse_fixes(output):
    if "no efix" in output.lower() or "no interim fix" in output.lower():return []
    rows=[]
    for line in output.splitlines():
        fields=line.split()
        if fields and fields[0].isdigit():
            if len(fields)<5:raise ValueError("Invalid AIX emgr row")
            rows.append({"name":fields[-1],"installed":" ".join(fields[2:-1]),"candidate":fields[1],"description":"AIX interim fix","source":"emgr","type":"interim_fix"})
    if not rows and output.strip() and "EFIX LABEL" not in output.upper():raise ValueError("Unrecognized AIX emgr output")
    return rows

def patches(client,options):
    if options.get("action","list")!="list":raise ValueError("AIX patch operations are read-only")
    packages=parse_filesets(read(client,"filesets"));level=read(client,"oslevel").strip();warnings=[]
    if not re.fullmatch(r"[0-9]+(?:-[0-9]+)*",level):raise ValueError("Invalid AIX oslevel result")
    try:packages+=parse_fixes(read(client,"fixes"))
    except ValueError as exc:warnings.append(str(exc))
    return {"action":"list","manager":"aix-installp","packages":packages,"oslevel":level,
            "output":"AIX OS level: "+level,"status":"partial" if warnings else "completed","warnings":"; ".join(warnings),
            "note":"AIX 설치 파일셋·임시 수정 조회 전용. 미설치 업데이트/APAR 전체 판정이 아니며 설치·커밋·제거·재부팅을 수행하지 않습니다. State는 AIX 원본 상태 코드입니다."}

def parse_resources(uptime,memory,filesystem):
    match=re.search(r"load averages?:\s*([0-9.]+)[, ]+([0-9.]+)[, ]+([0-9.]+)",uptime)
    if not match:raise ValueError("Invalid AIX uptime/load averages")
    pages={}
    for line in memory.splitlines():
        m=re.fullmatch(r"\s*(\d+)\s+(memory pages|free pages)\s*",line)
        if m:pages[m[2]]=int(m[1])
    total=pages.get("memory pages",0);free=pages.get("free pages",-1)
    if total<=0 or not 0<=free<=total:raise ValueError("Invalid AIX memory page counters")
    lines=[line.split() for line in filesystem.splitlines() if line.strip()]
    fields=next((f for f in reversed(lines) if len(f)>=6 and f[-1]=="/"),None)
    if fields is None or not re.fullmatch(r"\d+%",fields[4]):raise ValueError("Invalid AIX POSIX df output")
    used,available=int(fields[2]),int(fields[3])
    if min(used,available)<0 or int(fields[4][:-1])>100:raise ValueError("Invalid AIX filesystem counters")
    duration=re.search(r"\bup\s+(.+?),\s*\d+\s+users?",uptime)
    return {"uptime":duration[1].strip() if duration else uptime.strip(),"load_average":[float(v) for v in match.groups()],
            "memory_mb":{"total":total//256,"free":free//256,"used":(total-free)//256},
            "root_filesystem":{"filesystem":fields[0],"used":str(used),"available":str(available),"capacity":fields[4],"mounted_on":"/"},
            "note":"AIX vmstat -v의 4 KiB 페이지를 MiB로 환산. 사용 메모리=전체-무료(파일 캐시 포함), Linux available과 다릅니다. Load는 CPU 사용률이 아닙니다."}

def resources(client):
    return parse_resources(read(client,"uptime"),read(client,"memory"),read(client,"filesystem"))

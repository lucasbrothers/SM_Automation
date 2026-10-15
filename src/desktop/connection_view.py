"""Pure snapshot filtering and bounded table pages; no Qt objects in workers."""


from datetime import datetime


def snapshot_time(row):
    value=row.get("observed_at")
    if not value:return "조회 이력 없음"
    try: value=datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError,TypeError): value="시각 확인 불가"
    return value+(" (과거 작업 시각)" if row.get("time_is_job_time") else "")


def filter_snapshot(snapshot, query):
    query=query.casefold().strip()
    if not query:return snapshot
    rows=[]
    for row in snapshot:
        host_match=query in (row['hostname']+' '+row['ip']).casefold()
        matches=[]
        for item in row.get('result',{}).get('connections',[]):
            local,remote=item['local'],item['remote']
            text=f"{local['address']}:{local['port']} {remote['address']}:{remote['port']}"
            if host_match or query in text.casefold():matches.append(item)
        if matches or host_match:rows.append({**row,'result':{**row.get('result',{}),'connections':matches}})
    return rows


def table_rows(snapshot):
    for row in snapshot:
        for item in row.get('result',{}).get('connections',[]):
            local,remote=item['local'],item['remote']
            yield [row['hostname'],f"{local['address']}:{local['port']}",remote['address'],str(remote['port']),snapshot_time(row)]


def table_page(snapshot, page, size=200):
    skip=(page-1)*size
    result=[]
    for row in snapshot:
        items=row.get('result',{}).get('connections',[])
        if skip>=len(items):skip-=len(items);continue
        chosen=items[skip:skip+size-len(result)];skip=0
        result.extend(table_rows([{**row,'result':{'connections':chosen}}]))
        if len(result)==size:break
    return result

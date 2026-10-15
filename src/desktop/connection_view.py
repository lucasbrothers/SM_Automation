"""Pure snapshot filtering and bounded table pages; no Qt objects in workers."""


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
            yield [row['hostname'],f"{local['address']}:{local['port']}",remote['address'],str(remote['port'])]


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

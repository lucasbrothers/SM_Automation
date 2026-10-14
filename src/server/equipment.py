"""Named equipment books with encrypted membership; hosts remain inventory identities."""
import uuid


def books(store):
    rows=store.read_json('equipment-books.json.enc',[])
    if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) or not isinstance(r.get('name'),str) or not isinstance(r.get('hosts'),list) for r in rows):
        raise ValueError('Equipment books require recovery')
    return rows


def get(store,identity,inventory):
    row=next((r for r in books(store) if r['id']==identity),None)
    if row is None:raise ValueError('Equipment book no longer exists')
    names={r['hostname'] for r in inventory}
    if not row['hosts'] or any(h not in names for h in row['hosts']):raise ValueError('Equipment book contains missing inventory hosts; edit it first')
    return row


def change(store,method,params,inventory):
    rows=books(store);identity=params.get('id')
    existing=next((r for r in rows if r['id']==identity),None)
    if method=='equipment.book.delete':
        if existing is None:raise ValueError('Equipment book no longer exists')
        rows.remove(existing);store.write_json('equipment-books.json.enc',rows);return {'id':identity}
    if identity and existing is None:raise ValueError('Equipment book no longer exists')
    name=params.get('name');description=params.get('description','');hosts=params.get('hosts')
    if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 for c in name):raise ValueError('Enter an equipment book name of 1–80 characters')
    if not isinstance(description,str) or len(description)>1000:raise ValueError('Description must be at most 1000 characters')
    if any(r['id']!=identity and r['name'].casefold()==name.strip().casefold() for r in rows):raise ValueError('Equipment book name already exists')
    known={r['hostname'] for r in inventory}
    if not isinstance(hosts,list) or not hosts or any(not isinstance(h,str) or h not in known for h in hosts):raise ValueError('Select existing inventory hosts')
    if not existing and len(rows)>=200:raise ValueError('At most 200 equipment books')
    record={'id':identity or uuid.uuid4().hex,'name':name.strip(),'description':description,'hosts':list(dict.fromkeys(hosts))}
    if existing:rows[rows.index(existing)]=record
    else:rows.append(record)
    store.write_json('equipment-books.json.enc',rows);return record

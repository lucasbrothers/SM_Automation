"""Encrypted reusable command library; templates never contain execution credentials."""

def library(store, method, params):
    rows = store.read_json('saved-commands.json.enc', default={})
    if not isinstance(rows, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in rows.items()):
        raise ValueError('Saved command library requires recovery')
    if method == 'command.saved.list':
        return [{'name': name, 'command': rows[name]} for name in sorted(rows, key=str.casefold)]
    name = params.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 for c in name):
        raise ValueError('Enter a command name of 1–80 characters')
    name = name.strip()
    if method == 'command.saved.save':
        command = params.get('command')
        if not isinstance(command,str) or not command.strip() or len(command)>16384 or '\x00' in command:
            raise ValueError('Command must be nonempty text up to 16384 characters')
        if name not in rows and len(rows)>=200: raise ValueError('At most 200 saved commands')
        rows[name] = command
    elif method == 'command.saved.delete':
        if name not in rows: raise ValueError('Saved command no longer exists')
        del rows[name]
    else: raise ValueError('Unknown saved command operation')
    store.write_json('saved-commands.json.enc', rows)
    return {'name': name, 'status': 'saved' if method.endswith('save') else 'deleted'}

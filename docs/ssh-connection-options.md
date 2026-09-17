# SSH Connection Options

## Connection summary

- Target host: 192.168.192.131
- Account: D25950
- Privilege switch: sudo su -
- Root transition is performed with the command `sudo su -`

## Recommended connection pattern

```python
client = SSHClient(
    "TEST01",
    "192.168.192.131",
    user="D25950",
    timeout=30,
    key_filename="/path/to/private_key",
)
```

### Real smoke-test invocation

```powershell
python scripts/ssh_key_smoke_test.py --host 192.168.192.131 --user D25950 --key-file C:/path/to/id_rsa --timeout 10
```

If a password-based login is ever needed, pass it only at runtime and never store it in the repo:

```powershell
python scripts/ssh_smoke_test.py --host 192.168.192.131 --user D25950 --timeout 10 --password "<runtime-secret>"
```

## Required authentication strategy

For the current test environment, key-based authentication is the preferred model.

```python
client = SSHClient(
    "TEST01",
    "192.168.192.131",
    user="D25950",
    timeout=30,
    key_filename="C:/path/to/id_rsa",
)
```

This is the safest default because the repository must not contain credentials.

## Root access flow

The current operational requirement is:

1. Log in as D25950
2. Execute `sudo su -`
3. Confirm root privileges with `id` or `whoami`

Example command flow:

```python
client.execute("id")
client.execute("sudo su -")
client.execute("id")
```

## Security notes

- Avoid storing passwords in repository files.
- Prefer SSH private keys and external secret storage.
- Do not log raw credentials or output containing sensitive values.
- Keep root privilege escalation explicit and auditable.

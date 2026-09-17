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

## Check the complete inventory

Use the inventory checker to confirm connection and collect `id`, hostname, and
OS/kernel information for every server. Passwords are read from an environment
variable and are not accepted as a command-line value.

Key-based check:

```powershell
python scripts/inventory_ssh_check.py `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa
```

Add `--check-root` to verify the configured `sudo su -` privilege transition:

```powershell
python scripts/inventory_ssh_check.py `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa `
    --check-root
```

Add `--report-file` to persist the results as JSON for later management or
monitoring workflows:

```powershell
py -3 scripts/inventory_ssh_check.py `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa `
    --check-root `
    --report-file reports/inventory-check.json
```

Password-based check:

```powershell
$env:SM_AUTOMATION_SSH_PASSWORD = "<runtime-secret>"
python scripts/inventory_ssh_check.py --inventory config/servers.test.txt
```

`[PASS]` shows the server was reached and information was collected. `[FAIL]`
shows the server-specific connection or command error. An inventory validation
error means the list must be corrected before any SSH connections are attempted.

## Copy a public key to the inventory

Use `sshkeycopy.py` to install the local public key in each target account's
`~/.ssh/authorized_keys`. The operation is idempotent and the password is read
from the environment or requested through a hidden interactive prompt.

```powershell
$env:SM_AUTOMATION_SSH_PASSWORD = "<runtime-secret>"
python scripts/sshkeycopy.py `
    --inventory config/servers.test.txt `
    --public-key-file C:/Users/seong/.ssh/id_rsa.pub `
    --user D25950
```

When `SM_AUTOMATION_SSH_PASSWORD` is not set, the command securely prompts for
the password instead:

```powershell
Remove-Item Env:SM_AUTOMATION_SSH_PASSWORD -ErrorAction SilentlyContinue
python scripts/sshkeycopy.py --inventory config/servers.test.txt
```

For a target that already accepts another private key, use `--key-file` instead
of setting the password environment variable. After a successful copy, rerun
`inventory_ssh_check.py` with that private key to verify key-based access.

## Run a read-only security audit

After SSH and root access are verified, collect the Linux security baseline:

```powershell
py -3 scripts/security_audit.py `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa `
    --report-file reports/security-audit.json
```

The audit reports UID 0 accounts, SSH authentication settings, and the
`sshd_config` ownership and mode. It does not modify the target servers.


## Collect Linux monitoring data

After SSH access is verified, collect read-only uptime, load, memory, and root
filesystem data for the inventory:

```powershell
py -3 scripts/monitoring_check.py `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa `
    --report-file reports/monitoring.json
```

The current collector targets Linux servers and does not change remote state.
This temporary collector is currently on hold; the target architecture is
`node-exporter` with Prometheus/Grafana integration.
## Evaluate security compliance

Policy evaluation is separate from collection. Select the OS/version policy
file, such as `config/security-policy-rhel9.json`, to match the approved
customer policy,
then evaluate the audit report:

```powershell
py -3 scripts/security_compliance.py `
    --audit-report reports/security-audit.json `
    --policy-file config/security-policy-rhel9.json `
    --report-file reports/security-compliance.json
```

Exit code `0` means all servers comply; exit code `1` means at least one
finding exists. Parameter meanings and recommended values are summarized in
`docs/security-policy.md`.

## Security notes

- Avoid storing passwords in repository files.
- Prefer SSH private keys and external secret storage.
- Do not log raw credentials or output containing sensitive values.
- Keep root privilege escalation explicit and auditable.

[CmdletBinding()]
param(
    [string]$PsqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe",
    [string]$ServiceName = "postgresql-x64-18",
    [string]$DatabaseName = "sm_automation",
    [switch]$RestartService
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PsqlPath -PathType Leaf)) {
    throw "psql.exe not found: $PsqlPath"
}

$password = Read-Host "PostgreSQL postgres password" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential("postgres", $password)
$env:PGPASSWORD = $credential.GetNetworkCredential().Password

try {
    $sql = @"
ALTER SYSTEM SET listen_addresses = 'localhost';
ALTER SYSTEM SET password_encryption = 'scram-sha-256';
ALTER SYSTEM SET log_connections = 'on';
ALTER SYSTEM SET log_disconnections = 'on';
ALTER SYSTEM SET log_checkpoints = 'on';
ALTER SYSTEM SET log_lock_waits = 'on';
ALTER SYSTEM SET log_line_prefix = '%m [%p] %u@%d %r ';
SELECT pg_reload_conf();
"@
    $sql | & $PsqlPath -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL security settings failed." }

    if ($DatabaseName) {
        $schemaSql = @"
REVOKE ALL ON SCHEMA public FROM PUBLIC;
"@
        $schemaSql | & $PsqlPath -h localhost -p 5432 -U postgres -d $DatabaseName -v ON_ERROR_STOP=1
        if ($LASTEXITCODE -ne 0) { throw "CMDB schema permission hardening failed." }
    }

    if ($RestartService) {
        Restart-Service -Name $ServiceName -Force
        Write-Host "[PASS] PostgreSQL service restarted: $ServiceName"
    }
    else {
        Write-Host "[INFO] Restart not requested. listen_addresses requires a service restart."
    }
    Write-Host "[PASS] Local PostgreSQL security settings applied."
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

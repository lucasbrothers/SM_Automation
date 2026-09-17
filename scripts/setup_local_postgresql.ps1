[CmdletBinding()]
param(
    [string]$PostgresHost = "localhost",
    [int]$PostgresPort = 5432,
    [string]$AdminUser = "postgres",
    [string]$DatabaseName = "sm_automation",
    [string]$ApplicationUser = "sm_automation",
    [string]$OwnerUser = "sm_automation_owner",
    [string]$PsqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
)

$ErrorActionPreference = "Stop"
$schemaFile = Join-Path $PSScriptRoot "..\config\cmdb-schema.sql"

if (-not (Test-Path $schemaFile -PathType Leaf)) {
    throw "CMDB schema file not found: $schemaFile"
}

$adminPassword = Read-Host "PostgreSQL administrator password" -AsSecureString
$adminCredential = New-Object System.Management.Automation.PSCredential($AdminUser, $adminPassword)
$env:PGPASSWORD = $adminCredential.GetNetworkCredential().Password
$applicationPassword = Read-Host "CMDB application user password" -AsSecureString
$applicationPasswordText = $applicationPassword -as [System.Security.SecureString]
$applicationPasswordPlain = (New-Object System.Management.Automation.PSCredential("temporary", $applicationPasswordText)).GetNetworkCredential().Password
$escapedApplicationPassword = $applicationPasswordPlain.Replace("'", "''")

try {
    & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c "SELECT version();"
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL administrator connection failed." }

    $createRoleSql = @"
DO `$`$`
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$OwnerUser') THEN
        CREATE ROLE $OwnerUser NOLOGIN;
    END IF;
END
`$`$;
DO `$`$`
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$ApplicationUser') THEN
        CREATE ROLE $ApplicationUser LOGIN;
    END IF;
END
`$`$;
ALTER ROLE $ApplicationUser LOGIN PASSWORD '$escapedApplicationPassword' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
"@
    $createRoleSql | & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "CMDB role creation/configuration failed." }

    $databaseExists = & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d postgres -At -c "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName';"
    if ($LASTEXITCODE -ne 0) { throw "CMDB database lookup failed." }
    if (-not ($databaseExists -match "1")) {
        & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DatabaseName OWNER $OwnerUser;"
        if ($LASTEXITCODE -ne 0) { throw "CMDB database creation failed." }
    }

    & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d $DatabaseName -v ON_ERROR_STOP=1 -f $schemaFile
    if ($LASTEXITCODE -ne 0) { throw "CMDB schema initialization failed." }

    $grantSql = @"
GRANT CONNECT ON DATABASE $DatabaseName TO $ApplicationUser;
GRANT USAGE ON SCHEMA public TO $ApplicationUser;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $ApplicationUser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $ApplicationUser;
"@
    $grantSql | & $PsqlPath -h $PostgresHost -p $PostgresPort -U $AdminUser -d $DatabaseName -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "CMDB application role grants failed." }

    Write-Host "[PASS] Local PostgreSQL CMDB initialized: $DatabaseName"
    Write-Host "[INFO] Set SM_AUTOMATION_CMDB_PASSWORD before enabling application access."
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $applicationPasswordPlain = $null
    $escapedApplicationPassword = $null
}

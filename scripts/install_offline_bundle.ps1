[CmdletBinding()]
param(
    [switch]$InstallPostgreSQL,
    [string]$PostgreSQLInstaller = "src\sw\postgresql-18.6-3-windows-x64.exe",
    [string]$PythonPath = "py",
    [string]$WheelDirectory = "src\sw\python-wheels"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$installer = Join-Path $root $PostgreSQLInstaller
$wheelPath = Join-Path $root $WheelDirectory
$requirements = Join-Path $root "requirements-runtime.txt"
$manifest = Join-Path $root "config\offline-package-manifest.json"

if (-not (Test-Path $manifest -PathType Leaf)) {
    throw "Offline package manifest not found: $manifest"
}
if (-not (Test-Path $installer -PathType Leaf)) {
    throw "PostgreSQL installer not found: $installer"
}

Write-Host "[PASS] PostgreSQL installer found: $installer"

if ($InstallPostgreSQL) {
    Write-Host "[INFO] Starting PostgreSQL installer. Complete the installer UI with the approved local settings."
    $process = Start-Process -FilePath $installer -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "PostgreSQL installer failed with exit code $($process.ExitCode)."
    }
    Write-Host "[PASS] PostgreSQL installer completed"
}
else {
    Write-Host "[INFO] Dry run only. Use -InstallPostgreSQL to start the installer."
}

if (Test-Path $wheelPath -PathType Container) {
    $wheels = @(Get-ChildItem $wheelPath -File)
    if ($wheels.Count -gt 0) {
        & $PythonPath -m pip install --no-index --find-links $wheelPath -r $requirements
        if ($LASTEXITCODE -ne 0) {
            throw "Offline Python package installation failed."
        }
        Write-Host "[PASS] Offline Python packages installed from $wheelPath"
    }
    else {
        Write-Warning "No wheel files found in $wheelPath. Python dependencies were not installed."
    }
}
else {
    Write-Warning "Wheel directory not found: $wheelPath. Add offline wheel files before deployment."
}

Write-Host "[INFO] Run scripts/setup_local_postgresql.ps1 after PostgreSQL installation."
Write-Host "[INFO] Use config/app.local.json for local CMDB configuration."

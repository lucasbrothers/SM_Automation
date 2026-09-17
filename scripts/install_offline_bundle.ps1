[CmdletBinding()]
param(
    [string]$PythonPath = "py",
    [string]$WheelDirectory = "src\sw\python-wheels"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$wheelPath = Join-Path $root $WheelDirectory
$requirements = Join-Path $root "requirements-runtime.txt"
$manifest = Join-Path $root "config\offline-package-manifest.json"

if (-not (Test-Path $manifest -PathType Leaf)) {
    throw "Offline package manifest not found: $manifest"
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

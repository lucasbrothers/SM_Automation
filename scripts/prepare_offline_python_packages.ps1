[CmdletBinding()]
param(
    [string]$PythonPath = "py",
    [string]$WheelDirectory = "src\sw\python-wheels"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$wheelPath = Join-Path $root $WheelDirectory
$requirements = Join-Path $root "requirements-runtime.txt"

New-Item -ItemType Directory -Force -Path $wheelPath | Out-Null
& $PythonPath -m pip download --only-binary=:all: --dest $wheelPath -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download offline Python packages."
}
Write-Host "[PASS] Offline Python package bundle prepared: $wheelPath"

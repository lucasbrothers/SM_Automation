[CmdletBinding()]
param([string]$PythonPath = "py", [string]$WheelDirectory = "wheelhouse\gui")
$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
& $PythonPath (Join-Path $PSScriptRoot "prepare_offline_packages.py") --role gui --destination (Join-Path $projectRoot $WheelDirectory)
if ($LASTEXITCODE -ne 0) { throw "Windows GUI wheel preparation failed." }
Write-Host "Linux server wheels must be prepared on a matching Linux machine with --role server."

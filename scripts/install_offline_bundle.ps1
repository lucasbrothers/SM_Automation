[CmdletBinding()]
param(
    [string]$PythonPath = "py",
    [string]$WheelDirectory = "wheelhouse\gui"
)
$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$wheelPath = Join-Path $projectRoot $WheelDirectory
if (-not (Test-Path -LiteralPath $wheelPath -PathType Container)) {
    throw "Prepare Windows GUI wheels first with scripts/prepare_offline_packages.py --role gui"
}
& $PythonPath -m pip install --no-index --find-links $wheelPath -r (Join-Path $projectRoot "requirements-gui.txt")
if ($LASTEXITCODE -ne 0) { throw "GUI dependency installation failed." }
Write-Host "GUI installed. Run scripts/run_desktop.py and connect to the Linux server on TLS port 7443."

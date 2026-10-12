param([string]$PublicCA)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
py -3.14 -m venv .venv-gui
if ($LASTEXITCODE -ne 0) { throw 'Python 3.14 with venv is required.' }
& .venv-gui/Scripts/python.exe -m pip install -r requirements-gui.txt
if ($LASTEXITCODE -ne 0) { throw 'GUI dependency installation failed.' }
if ($PublicCA) {
    certutil -user -addstore Root $PublicCA
    if ($LASTEXITCODE -ne 0) { throw 'Public CA installation failed.' }
}
Write-Output 'Installed. Start with deploy/start-gui.cmd.'

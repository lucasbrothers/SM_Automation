param([switch]$Demo, [switch]$Check)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = @('.venv-gui', '.venv') | Where-Object {
    Test-Path -LiteralPath (Join-Path $projectRoot "$_/Scripts/python.exe")
} | Select-Object -First 1
if (-not $runtimeDirectory) {
    throw 'GUI environment missing. Follow docs/deployment.md to install requirements-gui.txt.'
}
$pythonPath = Join-Path $projectRoot "$runtimeDirectory/Scripts/python.exe"
& $pythonPath -c 'import PySide6'
if ($LASTEXITCODE -ne 0) {
    throw 'PySide6 is unavailable. Install requirements-gui.txt into the selected environment.'
}
if ($Check) {
    Write-Output "GUI environment ready: $runtimeDirectory"
    return
}
$windowedPython = Join-Path $projectRoot "$runtimeDirectory/Scripts/pythonw.exe"
if (-not (Test-Path -LiteralPath $windowedPython)) {
    throw 'Windowed Python is unavailable in the GUI environment.'
}
$launcherPath = Join-Path $PSScriptRoot 'run_desktop.py'
if ($Demo) {
    & $windowedPython $launcherPath --demo
} else {
    & $windowedPython $launcherPath
}

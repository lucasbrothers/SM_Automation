@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" "scripts\run_wsl_desktop.py"
if errorlevel 1 pause

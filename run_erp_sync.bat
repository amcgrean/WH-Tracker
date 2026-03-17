@echo off
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
powershell.exe -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_erp_sync.ps1"

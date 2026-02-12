@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python sync_erp.py
pause

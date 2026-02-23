@echo off
:: ============================================================
:: run_email_sync.bat
:: Polls the inbox for RMA credit emails and saves images.
::
:: Schedule with Windows Task Scheduler:
::   - Action: Start a Program
::   - Program/script: C:\path\to\WH-Tracker\run_email_sync.bat
::   - Trigger: Every 15 minutes (or whatever interval you prefer)
::
:: The script activates the Python virtual environment (if present),
:: then runs the sync script.
:: ============================================================

cd /d "%~dp0"

:: If you use a venv, activate it; otherwise just use system Python
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python sync_email_credits.py

:: Pause only when run interactively (not via Task Scheduler)
if "%1"=="--interactive" pause

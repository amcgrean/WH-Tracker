# ERP Sync Architectural Pattern: Local-to-Cloud Automation

This document outlines the robust pattern for synchronizing local business data (ERPs, CSVs, SQL) with a cloud-based web application (Vercel/Neon/Postgres).

## 1. High-Level Architecture
1. **Source**: Local CSVs or a Legacy Database on a business PC/Server.
2. **Ingestor**: A local Python script (`import_data.py`) that parses source data and performs UPSERT (Update or Insert) operations on the cloud database.
3. **Local Orchestrator**: A PowerShell script (`run_erp_sync.ps1`) that handles retries, .env loading, and logging.
4. **Local Trigger**: Windows Task Scheduler running a `.bat` wrapper daily.
5. **Cloud Sync (Optional/Secondary)**: A secure API endpoint within the web app for manual or remote-triggered syncs via Vercel Crons.

---

## 2. Local Sync Implementation (Python + PowerShell)

### The Core Logic (`import_data.py`)
- Uses SQLAlchemy to connect directly to the cloud Postgres instance via `DATABASE_URL`.
- Maps CSV columns to Database Model attributes.
- Uses idempotent logic to ensure records aren't duplicated on every run.

### The Robust Orchestrator (`run_erp_sync.ps1`)
- **Environment**: Loads `.env` file variables into the process scope.
- **Retries**: Uses an exponential backoff loop (e.g., 3 retries) to handle network jitters.
- **Logging**: Captures `stdout` and `stderr` to a dated log file in a `/logs` directory.

### The Trigger Wrapper (`run_erp_sync.bat`)
```batch
@echo off
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
powershell.exe -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_erp_sync.ps1"
```

---

## 3. Remote Sync Implementation (API + Vercel Cron)

### Secure API Endpoint
- **Path**: `/api/cron/sync-erp`
- **Security**: Verifies a `Bearer` token against a `CRON_SECRET` environment variable.
- **Trigger**: Can be called via `curl` or Vercel's Cron scheduler.

### Vercel Configuration (`vercel.json`)
```json
{
  "crons": [
    {
      "path": "/api/cron/sync-erp",
      "schedule": "0 0 * * *"
    }
  ]
}
```

---

## 4. Security Best Practices
- **Credential Isolation**: Store all database URLs and keys in encrypted environment variables (production) or `.env` files (local).
- **Execution Policy**: Use `-ExecutionPolicy Bypass` only within the context of the specific automation task.
- **Whitelist**: If possible, restrict database access to specific IP ranges (though difficult with Vercel serverless IPs).

## 5. Deployment Checklist for AI Agents
- [ ] Verify cloud database connectivity from local environment.
- [ ] Ensure Python `venv` is active and requirements installed.
- [ ] Configure `CRON_SECRET` in both code and Vercel dashboard.
- [ ] Test the local orchestration script manually before scheduling.
- [ ] Set up Windows Task Scheduler to run as a user with file permissions for the CSV sources.

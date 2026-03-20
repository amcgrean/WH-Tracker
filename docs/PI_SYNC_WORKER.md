# Pi Sync Worker

This project now supports a single tracker-root environment contract for both the web app and the ERP mirror worker.

## Goal

Run `sync_erp.py` on an always-on machine such as a Raspberry Pi so tracker does not depend on a user PC staying awake.

## Environment

Copy [`.env.example`](/C:/Users/amcgrean/python/tracker/.env.example) to `tracker/.env` and fill in:

- `SQLSERVER_DSN` for the preferred local ERP connection
- or `SQLSERVER_SERVER` / `SQLSERVER_DB` / `SQLSERVER_USER` / `SQLSERVER_PASSWORD`
- `DATABASE_URL` for the mirror database
- `SYNC_INTERVAL_SECONDS=5`
- `SYNC_CHANGE_MONITORING=true`
- `SYNC_WORKER_NAME` and `SYNC_WORKER_MODE=pi`

## Runtime Behavior

- The worker always reads from local ERP SQL, even if the tracker web app is running in `CLOUD_MODE=true`.
- The worker computes a payload hash every cycle.
- If no changes are detected, it records a `noop` heartbeat instead of pushing duplicate data.
- If changes are detected, it syncs picks, work orders, and delivery KPIs directly into the mirror database.
- Heartbeats and errors are written to:
  - database table `erp_sync_state` when `DATABASE_URL` is available
  - `logs/erp_sync_status.json` on disk for local diagnostics

## Status Visibility

Tracker now exposes sync health at:

- `/api/sync/status`

That endpoint reports the most recent worker heartbeat, status, counts, and whether the heartbeat is stale.

## Starting the Worker

Windows:

```powershell
.\run_erp_sync.ps1
```

Cross-platform:

```bash
python sync_erp.py
```

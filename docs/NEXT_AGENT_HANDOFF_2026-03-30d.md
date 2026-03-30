# Agent Handoff — 2026-03-30 Session 4 (Deployment Fix + Query Perf)

## What Was Done

### 1. Fixed Fly.io Deployment Failure (4 commits, all merged to main)

The app was failing to start on Fly.io with "App is not listening to the expected port" error. Root causes and fixes:

- **Duplicate Alembic revision ID** — Two migration files shared `k5l6m7n8o9p0` (merge migration + add-branch-to-users). Renamed the add-branch migration to `k5l6m7n8o9p0b` and fixed the dependency chain. Single head: `m7n8o9p0q1r2`.

- **Migration race condition** — Both Fly machines ran migrations simultaneously, causing DB lock contention. Added `pg_try_advisory_lock()` around `_run_migrations()` so only one machine runs DDL; the other skips gracefully.

- **Health check blocked by auth** — `/healthz` was not in `public_endpoints`, so when `AUTH_REQUIRED=true`, Fly health checks got 302'd to login. Added `main.root_health` and `dispatch.health` to exemptions.

- **Deploy strategy** — Both machines updated simultaneously despite "rolling" label. Added `[deploy] strategy = "rolling"` to `fly.toml`. Also increased health check grace_period 20s→60s and timeout 5s→10s.

### 2. Supabase Query Performance Fix (merged to main)

The main board query (`get_open_picks`) was averaging 7-11s and was the top CPU consumer:

- **`shipment_rollup` CTE** — Was aggregating ALL 1M+ rows with no filter. Added recency filter: `invoice_date >= CURRENT_DATE - 180 days OR ship_date >= 180 days OR status NOT IN ('C','X')`.

- **`pick_rollup` CTE** — No row limit. Added `created_date >= CURRENT_DATE - 30 days` filter.

- **Redundant CAST removal** — Removed ~20 instances of `CAST(col AS TEXT)` on `so_id` and `item_ptr` joins across the entire `erp_service.py`. All these columns are already `VARCHAR(64)` — the CASTs were preventing index usage. Fixed in `get_open_picks`, `get_wo_for_so`, `get_open_summary`, `get_historical_so_summary`, `search_items`, `get_open_work_orders`, and 6+ other query methods.

Expected improvement: 7-11s → under 500ms.

### 3. Auth Exemptions (Kodex PRs #86 + #87, merged to main)

Kodex agent handled kiosk/TV/pick-tracker auth exemptions:
- `/kiosk/`, `/tv/` path prefixes exempt
- Legacy pick tracker paths exempt: `/pick_tracker`, `/confirm_picker/`, `/input_pick/`, `/complete_pick/`, `/start_pick/`, `/api/smart_scan`
- Health endpoints exempt from auth

## Current State

- **Branch**: `claude/fix-deployment-error-TvTWt` — now at main tip, all work merged
- **Alembic head**: `m7n8o9p0q1r2` (dispatch planning tables)
- **fly.toml**: rolling deploy, 60s grace, 10s timeout
- **Production URL**: https://wh-tracker-fly.fly.dev
- **Deploy**: In progress as of session end

## What's Left (Priority Order)

### P1 — Verify Deploy
- Confirm Fly deploy succeeds with the rolling strategy + health check fixes
- If machine `9185461dc19308` still fails, destroy and recreate it from Fly dashboard — it failed in 3 consecutive deploys

### P1 — Open PR #88 (Delivery Reporting Dashboard)
- Branch: `codex/delivery-reporting-manager-dashboard`
- Adds delivery reporting service, manager dashboard, JSON/export endpoints, `manager` role
- Status: open, mergeable, needs review

### P2 — Unmerged Kodex Template Cleanup
- Commit `c4d96bf` on `codex/kiosk-auth-exclusions` branch
- Converts legacy pick tracker templates (`index.html`, `confirm_picker.html`, `input_pick.html`, `complete_pick.html`) from `base.html` to `kiosk_base.html`
- Removes CSS hacks (hidden sidebar, hover-zone toolbar) in favor of clean kiosk shell
- Cosmetic only — pick tracker works fine either way
- Needs a PR to merge

### P2 — Seed Real Users
- Only 2 users exist: `amcgrean@beisserlumber.com` (admin) and `po-test@beisserlumber.com` (test)
- Add ops/supervisor/warehouse/sales staff via `/auth/users`
- Required before flipping `AUTH_REQUIRED=true` for real

### P3 — Manual Testing
- PO check-in wizard: login → scan PO → photo → submit → review
- Dispatch console: 4-zone layout, stop loading, route creation, drag-drop, truck panel, keyboard shortcuts, manifest PDF

### P3 — PO Search Performance
- `app_po_*` views are regular (not materialized) over 295k+ POs
- Best fix: convert to materialized views in Supabase with `pg_cron` refresh
- Current workaround: search returns max 25 rows, list has LIMIT 500

## Architecture Notes for Next Agent

### Pick Tracker vs Kiosk — Already Migrated
Both kiosk (`/kiosk/<branch>/...`) and legacy pick tracker (`/pick_tracker`, `/confirm_picker/`, etc.) are **fully on PostgreSQL mirror** via ERPService `central_db_mode`. Neither uses direct SQL Server. The only difference is UI: kiosk has touch-optimized `kiosk_base.html` templates; pick tracker uses `base.html` with CSS overrides. Legacy SQL Server fallback requires explicit `ENABLE_LEGACY_ERP_FALLBACK=true` env var (disabled by default, marked for troubleshooting only).

### Migration Safety
- Advisory lock (`pg_try_advisory_lock(7483201)`) ensures only one Fly machine runs migrations
- `_resolve_branched_alembic_state()` auto-cleans duplicate rows in `alembic_version`
- Always use `IF NOT EXISTS` guards in ALTER TABLE migrations for idempotency

### Query Performance Rules
- Never use `CAST(col AS TEXT)` on joins where both sides are already `VARCHAR` — breaks index usage
- CTEs that aggregate entire tables must have recency filters (date range or status filter)
- `so_id`, `item_ptr` are `VARCHAR(64)` everywhere — no CAST needed
- `cust_key`, `seq_num` still need `TRIM()` due to padding differences

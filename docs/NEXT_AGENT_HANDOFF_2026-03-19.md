# Next Agent Handoff - 2026-03-19

## Branch / Repo State

- Repo: `C:\Users\amcgrean\python\tracker`
- Active branch: `codex/tracker-staging-dispatch`
- Recent pushed commits on this branch:
  - `8349134` `Stabilize central mirror routes and migrations`
  - `c17824f` `Harden supervisor dashboard and shared nav`
  - `ba1f046` `Harden serverless database behavior`
  - `5612142` `Document Supabase tracker cutover`

There is still unrelated local churn in the worktree. Do not blanket-add or revert unrelated files.

## Supabase Cutover Status

### Local env state already changed

Local-only file updated:

- `C:\Users\amcgrean\python\tracker\.env`

Current local env behavior:

- `DATABASE_URL` now points to the Supabase pooler URL from `beisser-api`
- `CENTRAL_DB_URL` now points to that same Supabase pooler URL
- old Neon URL preserved locally as `LEGACY_DATABASE_URL`
- `DB_USE_NULL_POOL=true`

This local `.env` change is not tracked in git.

### Core Tracker-owned tables migrated from Neon to Supabase

Migration was run successfully with:

- `C:\Users\amcgrean\python\tracker\migrate_tracker_tables_to_supabase.py`

Successful copied tables:

- `PickTypes`
- `pickster`
- `pick`
- `pick_assignments`
- `work_orders`
- `customer_notes`
- `audit_events`
- `credit_images`

Verified target counts on Supabase after the successful core migration:

- `PickTypes = 2`
- `pickster = 20`
- `pick = 7`
- `pick_assignments = 0`
- `work_orders = 0`
- `customer_notes = 0`
- `audit_events = 0`
- `credit_images = 0`

### Legacy cache tables were NOT fully migrated

The script originally tried to move these too:

- `erp_mirror_picks`
- `erp_mirror_work_orders`
- `erp_delivery_kpis`

That bulk copy was intentionally backed off because the Supabase pooler was a poor fit for the large one-time insert volume and left stale idle-in-transaction sessions that had to be terminated.

The script was then changed so that:

- core app-owned tables migrate by default
- legacy cache tables only migrate if `INCLUDE_LEGACY_MIRROR_TABLES` is explicitly set

This was the right call because Tracker should now prefer normalized mirror reads through `CENTRAL_DB_URL` instead of relying on the old cache tables.

## Runtime Verification Already Done

Verified after the env flip:

- `ERPService` reports `CENTRAL_DB_MODE=True`
- `.\venv\Scripts\python.exe .\verify_route_smoke.py` still passes

The smoke output after the cutover showed:

- sales routes still render
- work order routes still render
- supervisor routes still render
- SQLite smoke migrations still run cleanly

## Important Reality Check

Tracker is NOT yet fully free of the old legacy cache models/tables.

### Remaining live references to `ERPMirrorPick` / `ERPMirrorWorkOrder`

Still present in:

- `C:\Users\amcgrean\python\tracker\app\Routes\routes.py`
- `C:\Users\amcgrean\python\tracker\app\Services\erp_service.py`
- model declarations in `C:\Users\amcgrean\python\tracker\app\Models\models.py`

High-signal hotspots:

#### In `app/Routes/routes.py`

- local pick state updates in:
  - `complete_pick()`
  - `start_pick()`
- legacy `/erp-cloud-sync` ingest endpoint
- `/api/confirm_staged/<so_number>`
- `/debug/counts`

#### In `app/Services/erp_service.py`

There are still many `if self.cloud_mode:` branches and helper fallbacks using:

- `ERPMirrorPick`
- `ERPMirrorWorkOrder`

Examples include:

- work order lookup fallback for a sales order
- open picks fallback
- open order summary fallback
- historical SO summary fallback
- SO detail fallback
- dispatch stop fallback
- sales metrics / reports fallback
- products / order history fallback

## Practical Meaning

### Safe to say now

- Tracker local app DB state has been moved to Supabase
- Tracker normalized mirror reads are now configured to use Supabase
- Sales, supervisor, and work-order smoke paths still pass with `CENTRAL_DB_MODE=True`

### NOT safe to say yet

- that the old legacy cache tables can be dropped immediately
- that Tracker is fully independent from `erp_mirror_picks` and `erp_mirror_work_orders`

## Best Next Steps

### 1. Replace remaining legacy cache reads in `ERPService`

Main next engineering task:

- convert remaining `ERPMirrorPick` / `ERPMirrorWorkOrder` code paths to normalized mirror equivalents

Focus first on:

- warehouse board / open summary helpers
- detailed SO item lookup helpers
- dispatch helper fallbacks
- sales helper fallbacks that still use `ERPMirrorPick`

### 2. Replace local pick-state writes that currently target `ERPMirrorPick`

In `app/Routes/routes.py`, these should move to a different local-state storage strategy rather than writing state back into the old cache model:

- `start_pick()`
- `complete_pick()`
- `confirm_staged()`

Potential approaches:

- write local state to app-owned tables only
- or write to normalized mirror companion state if a deliberate schema exists

Do NOT casually repurpose normalized mirror source tables for local workflow state without thinking through ownership.

### 3. After code is fully off legacy tables

Then:

- run a final reference audit for `ERPMirrorPick` / `ERPMirrorWorkOrder`
- remove legacy `/erp-cloud-sync` path if no longer needed
- decide whether to keep the legacy cache tables in Supabase as temporary ballast or retire them entirely

## Notes About the Supabase Pooler

- The pooled URL is good for app runtime traffic.
- It was not good for the large one-time legacy cache migration attempts.
- During those attempts, stale idle-in-transaction sessions had to be cleaned up with `pg_terminate_backend`.

If the legacy cache tables still need to be copied later, prefer:

- a smaller chunked migration path
- or a direct DB connection / admin migration path rather than the pooler

## Files Added or Updated in This Session That Matter

Tracked:

- `C:\Users\amcgrean\python\tracker\migrate_tracker_tables_to_supabase.py`
- `C:\Users\amcgrean\python\tracker\docs\CENTRAL_AGILITY_MIRROR_CUTOVER.md`
- `C:\Users\amcgrean\python\tracker\.env.example`
- `C:\Users\amcgrean\python\tracker\docs\NEXT_AGENT_HANDOFF_2026-03-19.md`

Local-only:

- `C:\Users\amcgrean\python\tracker\.env`

## One-Line Handoff

Tracker now points locally at Supabase for both app DB and normalized mirror reads, the core Tracker-owned tables have been copied from Neon into Supabase, smoke checks still pass with `CENTRAL_DB_MODE=True`, but the app is not yet fully free of the old `ERPMirrorPick` / `ERPMirrorWorkOrder` cache tables, so the next agent should finish those code-path conversions before dropping the legacy tables.

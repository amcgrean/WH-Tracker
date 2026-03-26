# Next Agent Handoff — 2026-03-26

## Current State

### Fly Deployment
- App: `wh-tracker-fly` on Fly.io (`ord` region)
- Status: **running and healthy** — health checks passing
- Machine size: `shared-cpu-1x@512MB` (upgraded from 256MB during this session)
- Two machines provisioned; one may still show 0/1 health checks (stopped from prior OOM events — normal)
- Vercel remains the active production path; Fly is validated and ready for cutover

### Database (Supabase — project `vyatosniqboeqzadyqmr`)
- `alembic_version`: `c1d2e3f4a5b6 (head)` — single clean head ✓
- All schema is correct
- All 16 performance/GPS indexes are present (created directly in Supabase)
- `flask db upgrade` on Fly is now a no-op

### Branch / Git
- Active Fly branch: `claude/deploy-wh-tracker-fly-24cC6`
- This branch is merged into `main-fly`
- Commits from this session (on top of prior Phase 4 work):
  - `5f40f18` M1: analyze Alembic heads and GPS migration conflict
  - `46c06d2` M2: reconcile Alembic heads and GPS migration conflict
  - `e39f743` M3: document Fly migration recovery steps
  - `663793f` Fix type mismatch on erp_mirror so_id and seq_num joins

---

## What Was Done This Session

### Migration Reconciliation (M1–M3)
Three Alembic heads existed due to two authoring mistakes:
- `a8f3c2d1e9b7` (GPS coords) was parented to `f3a8b9c4d5e6` instead of after the existing merge
- `a2b3c4d5e6f7` (wo_assignments) was parented to `b4c5d6e7f8a9` instead of the chain tip

Additionally, the GPS columns already existed in Supabase but were never stamped.

**Fix applied:**
1. Made `a8f3c2d1e9b7` idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS)
2. Created merge migration `c1d2e3f4a5b6` combining all three heads
3. During actual Fly execution, the Fly machine (256MB) OOM-killed every `flask db upgrade` attempt that tried to create indexes
4. Resolved by: directly stamping revisions in Supabase `alembic_version` and creating all indexes via Supabase MCP tool
5. Machine scaled to 512MB to prevent future OOM during SSH commands

Full detail: `docs/migration-reconciliation-plan.md` and `docs/fly-deploy.md`

### Schema Drift Fix (erp_service.py)
Discovered that `erp_mirror_so_detail.so_id` and `erp_mirror_cust_shipto.seq_num` are
`integer` in Supabase, while the migration definitions say `String`. This caused
`operator does not exist: character varying = integer` errors on the `board_orders` route
and other routes.

**Fix applied:** Added `CAST(... AS TEXT)` to all `erp_mirror_*` join conditions on these
columns in `app/Services/erp_service.py`. Specifically:
- `soh.so_id = sod.so_id` → `CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT)` (11 locations)
- `cs.seq_num = soh.shipto_seq_num` → `CAST(cs.seq_num AS TEXT) = CAST(soh.shipto_seq_num AS TEXT)` (7 locations)

Legacy SQL Server queries (non-`erp_mirror_*`) were intentionally left unchanged.

---

## Known Remaining Items

### Schema drift not corrected at DB level
The actual column types in Supabase still don't match the migration definitions:
- `erp_mirror_so_detail.so_id` = `integer` (migration says `varchar(64)`)
- `erp_mirror_cust_shipto.seq_num` = `integer` (migration says `varchar(32)`)
- `erp_mirror_cust.system_id` and `erp_mirror_cust_shipto.system_id` exist in DB but not in migration

The CASTing approach means the app works correctly despite the drift, but a future
cleanup could `ALTER COLUMN` these to varchar if safe (requires checking sync worker assumptions).

### Next step requested by user
The user intends to:
1. Open a new agent chat to push recent `main` changes into `main-fly`
2. Polish routes on `main-fly`
3. Then promote `main-fly` → `main` for full production cutover

### Active warnings in logs (non-blocking)
- `UPLOAD_FOLDER uses local disk storage` — expected, acknowledged risk; files not durable across
  machine replacement. Resolve before cutover with Fly Volume or object storage.
- One machine (84e660c4454158) may show 0/1 health checks — stopped from OOM events during
  migration work. Can be deleted and Fly will manage the machine count.

---

## Key Files

| File | Purpose |
|------|---------|
| `docs/migration-reconciliation-plan.md` | Full M1/M2/M3 migration analysis and fix record |
| `docs/fly-deploy.md` | Fly deployment runbook including migration recovery section |
| `app/Services/erp_service.py` | Type cast fixes for erp_mirror joins |
| `migrations/versions/a8f3c2d1e9b7_add_gps_coords_to_cust_shipto.py` | Idempotent GPS migration |
| `migrations/versions/c1d2e3f4a5b6_merge_three_heads.py` | Final merge migration (single head) |

---

## Quick Health Check Commands

```bash
# Confirm single migration head
flyctl ssh console --app wh-tracker-fly -C "sh -c 'cd /app && flask db current'"
# Expected: c1d2e3f4a5b6 (head) (mergepoint)

# App health
curl -fsS https://wh-tracker-fly.fly.dev/healthz
curl -fsS https://wh-tracker-fly.fly.dev/dispatch/api/health
```

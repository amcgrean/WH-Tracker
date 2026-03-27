# Next Agent Handoff — 2026-03-27 (Session B)

## Current State

### UI/UX Overhaul — COMPLETE (Phases 0-7)
All 8 phases of the frontend architecture overhaul are complete. Full spec in `docs/phase 1 audit.md`.

### What Was Done This Session

#### Bug Fix: Customer Names/Addresses Still Blank (commit `c602499`)

**Root cause:** The previous TRIM fix (commit `9c86671`) was necessary but insufficient. The actual root cause was a **`system_id` mismatch** on customer JOIN conditions.

- `erp_mirror_cust` and `erp_mirror_cust_shipto` store ALL customers under `system_id = '00CO'` (centralized customer master)
- `erp_mirror_so_header` orders use branch-specific system_ids: `10FD`, `20GR`, `25BW`, `30CD`, `40CV`
- Every query joined on `c.system_id = soh.system_id`, which caused **100% of non-00CO branch orders** to return NULL for all customer fields

**Fix:** Removed `system_id` from all 20 `erp_mirror_cust` / `erp_mirror_cust_shipto` LEFT JOIN conditions across all central_db_mode queries in `erp_service.py`. TRIM on `cust_key` and `seq_num` was retained.

**Verification against live Supabase:**
- Before fix: 1,029,851 orders → **0** matched customers
- After fix: 1,029,851 orders → **1,029,797** matched customers (99.99%)

**Important rule for future queries:** Customer/shipto mirror table joins must:
- Use `TRIM()` on `cust_key` and `seq_num`
- **NOT** join on `system_id` (customers are centralized, orders are branch-specific)
- Other mirror tables (so_header, so_detail, shipments, items, picks) correctly use `system_id` joins

SQL Server legacy-path queries (joining to `cust`/`cust_shipto`, not mirror tables) are unaffected — they correctly use `system_id`.

#### PWA Placeholder Icons
- Created `app/static/icons/icon-192.png` and `icon-512.png` — simple green squares matching theme color `#004526`
- These are functional placeholders; replace with branded Beisser icons when available

---

## Fly Deployment
- App: `wh-tracker-fly` on Fly.io (`ord` region)
- Status: **running and healthy**
- Machine size: `shared-cpu-1x@512MB`
- Vercel remains the active production path; Fly is validated and ready for cutover

### Database (Supabase — project `vyatosniqboeqzadyqmr`)
- `alembic_version`: `c1d2e3f4a5b6 (head)` — single clean head
- Schema drift on `so_id`/`seq_num` integer vs varchar — handled via CAST in erp_service.py
- Customer tables have `system_id` column in DB (added outside migrations) but NOT in SQLAlchemy model — model is out of sync but raw SQL queries work fine

### Database Key Facts
| Table | system_id values | Notes |
|-------|-----------------|-------|
| `erp_mirror_cust` | `00CO`, `NONE` | Centralized — 4,921 rows |
| `erp_mirror_cust_shipto` | `00CO`, `1`, `NONE` | Centralized — 144,979 rows |
| `erp_mirror_so_header` | `00CO`, `10FD`, `20GR`, `25BW`, `30CD`, `40CV` | Branch-specific |

---

## Deferred / Follow-up Items

### Must-do before cutover
1. **Kiosk/TV branch-aware data filtering** — Routes exist but data shows all branches with notice (Phase 2/3 partial)
2. **UPLOAD_FOLDER** — Uses local disk storage, not durable across machine replacement. Needs Fly Volume or object storage.
3. **PWA icons** — Replace placeholder green squares with branded Beisser icons

### Nice-to-have
4. **Pick module branch migration** — Add `branch_code` to Pickster, Pick, PickAssignment, WorkOrderAssignment (DB migration required)
5. **Schema drift cleanup** — ALTER COLUMN `erp_mirror_so_detail.so_id` and `erp_mirror_cust_shipto.seq_num` to varchar if safe
6. **Model sync** — Add `system_id` to `ERPMirrorCustomer` and `ERPMirrorCustomerShipTo` SQLAlchemy models (column exists in DB but not in model)

### Branch status
- `main-fly` is ahead of `main` — ready for PR/merge when user is ready for production cutover

---

## Commit History (recent)
```
c602499 Fix customer names/addresses: remove system_id from mirror customer joins
17bc923 Update next-agent-prompt and handoff docs with TRIM fix details
9c86671 Fix blank customer names/addresses across all central_db_mode queries
21ab59c Update next-agent-prompt for kiosk/TV branch filtering and cleanup
17693e6 Add agent handoff docs and updated next-agent-prompt for post-overhaul work
94ba468 Phases 5-7: supervisor/warehouse consistency, sales visual polish, legacy refresh + PWA
```

---

## Key Files

| File | Purpose |
|------|---------|
| `app/Services/erp_service.py` | All ERP queries — central_db_mode (mirror) + legacy SQL Server |
| `app/static/css/style.css` | Global design system with all shared CSS classes |
| `app/static/manifest.json` | PWA manifest |
| `app/static/service-worker.js` | Shell asset caching service worker |
| `app/static/icons/` | PWA icons (placeholder) |
| `app/branch_utils.py` | Branch constants, normalization, DSM expansion |
| `app/templates/base.html` | Shell: sidebar, branch selector, search, PWA registration |
| `docs/phase 1 audit.md` | Full UI/UX overhaul specification |

---

## Quick Health Check Commands

```bash
# Fly app health
curl -fsS https://wh-tracker-fly.fly.dev/healthz
curl -fsS https://wh-tracker-fly.fly.dev/dispatch/api/health

# Migration head
flyctl ssh console --app wh-tracker-fly -C "sh -c 'cd /app && flask db current'"
# Expected: c1d2e3f4a5b6 (head)
```

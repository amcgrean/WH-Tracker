# Database Schema Issues — Handoff for API Agent

Last updated: 2026-03-27

## 1. `so_id` type mismatch (integer vs varchar)

- `erp_mirror_so_detail.so_id` is **integer**
- `erp_mirror_so_header.so_id` is **varchar**
- **Impact:** Every join between these two tables needs `CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT)`
- **Fix:** `ALTER TABLE erp_mirror_so_detail ALTER COLUMN so_id TYPE VARCHAR(64);` (check for downstream dependencies first)

## 2. `seq_num` type mismatch (integer vs varchar)

- `erp_mirror_cust_shipto.seq_num` is **integer** in DB
- `erp_mirror_so_header.shipto_seq_num` is **varchar**
- **Impact:** Joins need `TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))`
- **Fix:** `ALTER TABLE erp_mirror_cust_shipto ALTER COLUMN seq_num TYPE VARCHAR(32);`

## 3. `system_id` column exists in DB but not in SQLAlchemy models

- `erp_mirror_cust` and `erp_mirror_cust_shipto` both have `system_id` in Supabase (added outside migrations)
- SQLAlchemy models `ERPMirrorCustomer` and `ERPMirrorCustomerShipTo` in `app/Models/models.py` do **not** declare `system_id`
- Works fine for raw SQL queries but ORM queries won't see it
- **Fix:** Add `system_id = db.Column(db.String(32), nullable=True, index=True)` to both models + create a migration

## 4. Customer join rules (critical query logic)

- `erp_mirror_cust` and `erp_mirror_cust_shipto` store ALL customers under `system_id = '00CO'`
- Orders in `erp_mirror_so_header` use branch-specific system_ids: `10FD`, `20GR`, `25BW`, `30CD`, `40CV`
- **Customer/shipto joins must NOT include `system_id`** — only use TRIM on `cust_key` and `seq_num`
- All other mirror table joins (so_header <-> so_detail, item_branch, shipments, picks) correctly use `system_id`

## 5. `vw_board_open_orders` Supabase view is broken/obsolete

- Missing `system_id`, customer names don't resolve due to the system_id join issue
- Replaced with a direct mirror-table query in `erp_service.py` (commit `3fa7b0e`)
- The view can be dropped in Supabase — it is no longer used by the app

## Quick reference — joins that need CASTs

| Join | Workaround in `erp_service.py` |
|------|-------------------------------|
| `so_header.so_id` <-> `so_detail.so_id` | `CAST(... AS TEXT)` both sides |
| `cust_shipto.seq_num` <-> `so_header.shipto_seq_num` | `TRIM(CAST(... AS TEXT))` both sides |
| `cust.cust_key` <-> `so_header.cust_key` | `TRIM(CAST(... AS TEXT))` both sides |

## Ideal fix SQL (run in Supabase SQL Editor when ready)

```sql
-- Fix 1: so_id type mismatch
ALTER TABLE erp_mirror_so_detail ALTER COLUMN so_id TYPE VARCHAR(64) USING so_id::VARCHAR;

-- Fix 2: seq_num type mismatch
ALTER TABLE erp_mirror_cust_shipto ALTER COLUMN seq_num TYPE VARCHAR(32) USING seq_num::VARCHAR;

-- Fix 5: drop obsolete view
DROP VIEW IF EXISTS vw_board_open_orders;
```

**After running the above**, the CAST workarounds in `erp_service.py` can be simplified to direct equality joins. The TRIM on `cust_key` should be kept since trailing whitespace from the ERP sync is a separate issue.

## Database key facts

| Table | system_id values | Notes |
|-------|-----------------|-------|
| `erp_mirror_cust` | `00CO`, `NONE` | Centralized — 4,921 rows |
| `erp_mirror_cust_shipto` | `00CO`, `1`, `NONE` | Centralized — 144,979 rows |
| `erp_mirror_so_header` | `00CO`, `10FD`, `20GR`, `25BW`, `30CD`, `40CV` | Branch-specific |

## Key files

- `app/Services/erp_service.py` — all ERP queries with the CAST workarounds
- `app/Models/models.py` — SQLAlchemy models (missing system_id on customer models)
- `migrations/versions/` — Alembic migration chain, current head: `j4k5l6m7n8o9`

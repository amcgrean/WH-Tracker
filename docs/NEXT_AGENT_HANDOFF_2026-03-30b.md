# Next Agent Handoff — 2026-03-30 (Session 2)

## Session Summary

This session fixed all schema mismatches in the PO Check-In module and verified the full data pipeline against production.

---

## What Was Done This Session

### 1. Verified app_po_* Views Exist

All four read-model views confirmed present and returning data:
- `app_po_search` — 295,318 rows in underlying `erp_mirror_po_header`
- `app_po_header` ✓
- `app_po_detail` ✓
- `app_po_receiving_summary` ✓

### 2. Fixed PO Service Schema Mismatches

The `po_service.py` was written against an assumed schema that didn't match the actual views. Fixed:

| Wrong column name | Actual column | File |
|---|---|---|
| `supplier_key` | `supplier_code` | `po_service.py` |
| `expected_date` | `expect_date` | `po_service.py`, `open_pos.html`, `open_po_detail.html` |
| `status` | `po_status` | `po_service.py`, `open_pos.html`, `open_po_detail.html`, `checkin.html` JS |
| `receive_complete` | `receipt_count` | `po_service.py`, `open_pos.html` |
| `total_qty_received` | `qty_received_total` | `open_po_detail.html` |
| `first_receipt_date` | `first_receive_date` | `open_po_detail.html` |
| `latest_receipt_date` | `last_receive_date` | `open_po_detail.html` |
| `latest_status` | `latest_recv_status` | `open_po_detail.html` |

Also fixed `list_open_pos_for_branch`: was querying `erp_mirror_po_header` which has no `po_number` or `branch_code` columns. Switched to `app_po_search` which has both.

### 3. Fixed Open POs Status Filter

ERP stores `'Canceled'` (one L), but the filter only excluded `'CANCELLED'` (two L's). Added `'CANCELED'` to the exclusion list so Canceled POs are filtered from the open-POs list.

### 4. Created Test User

`po-test@beisserlumber.com` (id=2, role=`purchasing`, branch=`20GR`) — created for reference but NOT usable for OTP login as this isn't a real mailbox. Admin (`amcgrean@beisserlumber.com`) can access all PO routes including the check-in wizard directly.

### 5. Verified End-to-End Data Pipeline

Confirmed all three service functions return correct data against production:
- `search_purchase_orders('305500')` → finds PO, correct keys
- `get_purchase_order('305500')` → header + 7 lines + receiving summary
- `list_open_pos_for_branch('10FD')` → returns open POs (non-canceled/closed)

---

## Current Production State

- **URL:** https://wh-tracker-fly.fly.dev
- **Alembic head:** `l6m7n8o9p0q1` (no new migrations this session)
- **Users:** id=1 amcgrean@beisserlumber.com (admin), id=2 po-test@beisserlumber.com (purchasing, non-functional email)
- **PO module:** Fully functional — routes, templates, service layer, DB views all working
- **Auth:** Email OTP only (Phase 1)

---

## What Needs To Happen Next

### Priority 1 — PO End-to-End Test (manual)

The automated data pipeline works. Still needs manual browser test:
1. Log in as `amcgrean@beisserlumber.com` (admin has access to all PO routes)
2. Go to `/po/` — 3-step wizard
3. Look up a real PO number (e.g. `305500` — Andersen Logistics, 10FD branch)
4. Take a photo (or use file picker to upload an image)
5. Submit
6. Review at `/po/review`

### Priority 2 — Add Real Users

Need to add actual warehouse/purchasing staff before the module goes live:
- Warehouse workers: role=`warehouse` or `purchasing`, branch set to their home branch
- Ops reviewers: role=`ops`, branch set
- Other admins/supervisors as needed

### Priority 3 — PO Search Performance (known issue)

The `app_po_search`, `app_po_header`, `app_po_detail`, and `app_po_receiving_summary` views are **regular views** (not materialized), confirmed via `information_schema.tables`. Every query against them re-runs the full aggregation live, which is expensive with 295k+ POs.

The underlying tables are well-indexed (`system_id`, `po_status`, `expect_date` all have btree indexes), so the filter predicates are pushed down — but the view's aggregations (receipt_count, qty totals, date aggregates) still execute on every request.

**Root cause:** `app_po_search` computes `receipt_count`, `qty_received_total`, `last_receive_date` etc. by joining `erp_mirror_po_header` to `erp_mirror_po_detail` and receipt tables on every query.

**Options (in order of impact):**
1. **Best:** Convert `app_po_search` to a `MATERIALIZED VIEW` in Supabase and schedule a periodic `REFRESH MATERIALIZED VIEW` (e.g. every 15 min). This is a Supabase-side change, not in this repo.
2. **Good:** For the open-PO list, bypass `app_po_search` and query `erp_mirror_po_header` directly for the list columns (it has `system_id`, `po_status`, `expect_date`, `supplier_name`, `supplier_code`). Derive po_number from `po_id::text` — verify this matches the po_number format in the view first.
3. **Quick win already applied:** `list_open_pos_for_branch` has `LIMIT 500` and filters by `system_id` and `po_status` before returning, so the index is used. The search endpoint (`/po/api/search`) only runs when the user types ≥2 chars and returns max 25 rows — acceptable.

**Note:** `erp_mirror_po_header` does NOT have a `po_number` column — the views compute it. Before switching to direct table queries for the list, check how `app_po_search.po_number` is derived (likely `po_id::text` or a join to another table).

### Priority 4 — Kiosk/TV Branch Filtering (still deferred)

WorkOrder routes and TV board can be branch-filtered (`branch_code` exists). Pick routes cannot yet. Full spec in prior `next-agent-prompt.md`.

### Priority 5 — Phase 2 Auth (mobile app, future)

Not started. SMS OTP + PIN login for warehouse/driver roles. Entry point: mobile app.

---

## Architecture Rules (permanent, do not regress)

1. **TRIM joins** — `central_db_mode` queries joining on `cust_key` or `seq_num` must use `TRIM()`.
2. **No system_id on customer joins** — `erp_mirror_cust` / `erp_mirror_cust_shipto` are centralized. Never join on `system_id`.
3. **admin bypass** — `@role_required` and `_is_allowed()` both short-circuit for `admin`. Keep in sync.
4. **IF NOT EXISTS on migrations** — Use raw SQL with `IF NOT EXISTS` guards for any columns that may have been applied outside Alembic.
5. **R2 for uploads** — New upload flows use R2 via boto3. Never `UPLOAD_FOLDER` for new features.
6. **No Supabase client** — SQLAlchemy + psycopg2 only.
7. **UPPER(COALESCE()) for string comparisons** — ERP data is mixed case. Always use `UPPER(COALESCE(col, ''))` and uppercase literals.
8. **expand_branch_filter()** — Never use `== branch` when branch could be `DSM`. DSM expands to `['20GR', '25BW']`.

---

## Key PO Module Files

| File | Purpose |
|------|---------|
| `app/Routes/po_routes.py` | PO blueprint — all routes |
| `app/Services/po_service.py` | PO query functions — corrected to match actual view schema |
| `app/templates/po/checkin.html` | 3-step check-in wizard |
| `app/templates/po/open_pos.html` | Open PO list (supervisor/admin) |
| `app/templates/po/open_po_detail.html` | Full PO detail + receiving summary + photo gallery |
| `app/templates/po/review_dashboard.html` | Submission review list with 15s polling |
| `app/templates/po/review_detail.html` | Single submission review form |
| `app/templates/po/history.html` | Worker's own submission history |

## Fly.io Quick Commands

```bash
fly deploy
fly logs --app wh-tracker-fly --no-tail
fly ssh console --app wh-tracker-fly -C "flask db current"
fly secrets list --app wh-tracker-fly
```

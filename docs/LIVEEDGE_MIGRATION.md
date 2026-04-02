# LiveEdge Migration — Agent Handoff

**Date**: 2026-04-02
**Source**: `amcgrean/WH-Tracker` (Python/Flask)
**Target**: `amcgrean/liveedge` (TypeScript)
**Database**: agility-api Supabase (shared — both apps read from same DB)

## Overview

WH-Tracker is a Flask warehouse operations platform being migrated to a
TypeScript codebase called LiveEdge. The ERP queries in this Python codebase
are the reference implementation. Before porting, they must comply with
Supabase query rules for the agility-api database.

This work is split into two phases.

---

## Phase 1: Fix Query Violations in WH-Tracker (Python)

These fixes ensure the queries are correct and performant before porting to
TypeScript. All changes are in `app/Services/erp/`.

### P1.1 — CRITICAL: Add system_id to all erp_mirror_cust joins

10 instances across 5 files where `LEFT JOIN erp_mirror_cust c` uses only
`cust_key` without `system_id`. Every one must add the system_id condition.

**Pattern to fix** (every cust join):
```sql
-- BEFORE (full table scan)
LEFT JOIN erp_mirror_cust c
    ON TRIM(c.cust_key) = TRIM(soh.cust_key)

-- AFTER (uses index)
LEFT JOIN erp_mirror_cust c
    ON c.system_id = soh.system_id
    AND TRIM(c.cust_key) = TRIM(soh.cust_key)
```

Same for `erp_mirror_cust_shipto` joins — add `cs.system_id = soh.system_id`.

**Files and approximate line numbers:**
- `erp/sales.py` — lines ~83, ~243, ~446, ~512, ~688 (5 instances)
- `erp/picks.py` — line ~88 (1 instance)
- `erp/dispatch.py` — line ~213 (1 instance)
- `erp/delivery.py` — line ~40 (1 instance)
- `erp/customers.py` — line ~129 (1 instance)
- `erp/orders.py` — check all cust joins too

### P1.2 — HIGH: Fix item_branch join in customers.py

```sql
-- BEFORE (missing system_id)
LEFT JOIN erp_mirror_item_branch ib ON ib.item_ptr = i.item_ptr

-- AFTER
LEFT JOIN erp_mirror_item_branch ib
    ON ib.system_id = sod.system_id
    AND ib.item_ptr = i.item_ptr
    AND ib.is_deleted = false
```

File: `erp/customers.py` line ~23 (get_sales_products)

### P1.3 — MEDIUM: Add system_id filter to COUNT in orders.py

File: `erp/orders.py` line ~375 — the handling code breakdown query
filters by `sod.so_id = :so_number` but not `sod.system_id`. Add
system_id to the WHERE clause.

### P1.4 — HIGH: Migrate dashboard queries to matviews

The following queries in the Python code hit raw mirror tables for
dashboard/list data. The LiveEdge TypeScript app should use matviews
instead. Document which matview replaces each query:

| Current query | Replacement matview/RPC |
|--------------|----------------------|
| `get_open_picks()` in picks.py | `app_mv_open_picks_by_branch` or `get_board_open_orders` RPC |
| `get_open_picks_count()` in picks.py | `app_mv_open_picks_by_branch` (pre-aggregated counts) |
| `get_open_order_board_summary()` in orders.py | `app_mv_board_open_orders` |
| Handling breakdown in picks.py | `app_mv_handling_by_branch` |
| Shipment status lookups | `app_mv_shipment_status_by_so` |

Note: The Python app still needs these raw queries for the SQL Server
fallback path. The matview migration is for the TypeScript port only.

### P1.5 — Verify is_deleted = false on all mirror queries

Spot check confirmed most queries have this. Do a final grep to verify
no new queries were added without it:
```bash
grep -n 'erp_mirror_' app/Services/erp/*.py | grep -v 'is_deleted'
```

---

## Phase 2: Port to LiveEdge TypeScript

This phase happens in the `amcgrean/liveedge` repository.

### What to port (by domain)

| Domain | Python source | Key queries | Matview available? |
|--------|-------------|-------------|-------------------|
| Dashboard/picks | `erp/picks.py` | open picks, counts, handling | Yes: `app_mv_open_picks_by_branch`, `app_mv_handling_by_branch` |
| Work orders | `erp/work_orders.py` | WO by barcode, open WOs | No — use mirror with system_id filter |
| Order board | `erp/orders.py` | open SO summary, board | Yes: `app_mv_board_open_orders` |
| SO detail | `erp/orders.py` | SO header, SO lines | No — use mirror with system_id filter |
| Dispatch | `erp/dispatch.py` | stops, enrichment, shipment lines | Partial: `app_mv_shipment_status_by_so` |
| Delivery | `erp/delivery.py` | tracker, KPIs, history | No — use mirror with system_id filter |
| Sales | `erp/sales.py` | hub metrics, transactions, invoice | No — use mirror with system_id filter |
| Customers | `erp/customers.py` | search, details, products, salespeople | No — use mirror with system_id filter |
| PO | `po_service.py` | PO search, detail | Yes: `app_po_header`, `app_po_detail` |
| Purchasing | `purchasing_service.py` | dashboards, queue, suggested buys | Uses app_po_* matviews |

### Key differences in TypeScript

1. **Use Supabase client** instead of raw SQL — `supabase.rpc()` and `supabase.from().select()`
2. **Use RPCs** for complex reads: `get_board_open_orders`, `get_po_detail`
3. **No SQL Server fallback** — LiveEdge is cloud-only (Supabase/PostgreSQL)
4. **All queries must include system_id** as first filter parameter
5. **Use matviews** wherever available instead of raw mirror tables

### Auth model

- WH-Tracker uses session-based OTP auth via `AppUser` table
- LiveEdge should use Supabase Auth or equivalent
- `estimating_user_id` column on `app_users` bridges to beisser-takeoff users

### File storage

- Both apps use Cloudflare R2 (S3-compatible)
- Bucket: `liveedgefiles` (default)
- Metadata tracked in `files` and `file_versions` PostgreSQL tables

---

## Agent Prompt for Phase 1

Copy this prompt to hand off the query fix work to another agent:

```
You are working on the WH-Tracker repository (amcgrean/WH-Tracker).
Branch: create a new branch from main.

## Task: Fix Supabase query violations in ERP service modules

The app is being migrated to a TypeScript codebase (amcgrean/liveedge) that
reads from the agility-api Supabase database. Before porting, all ERP
queries must comply with Supabase indexing rules.

### Rules
1. Every query on erp_mirror_* tables MUST filter by system_id first
2. Every LEFT JOIN on erp_mirror_cust must include system_id in the join
3. Every LEFT JOIN on erp_mirror_cust_shipto must include system_id in join
4. Joins between so_detail and item_branch must use BOTH (system_id, item_ptr)
5. All direct mirror table queries must include is_deleted = false
6. Do NOT add new indexes

### What to fix

All files are in app/Services/erp/:

**1. Add system_id to erp_mirror_cust joins (10 instances, CRITICAL)**

Files: sales.py, picks.py, dispatch.py, delivery.py, customers.py, orders.py

Find every instance of:
  LEFT JOIN erp_mirror_cust c ON TRIM(c.cust_key) = TRIM(soh.cust_key)
Replace with:
  LEFT JOIN erp_mirror_cust c ON c.system_id = soh.system_id AND TRIM(c.cust_key) = TRIM(soh.cust_key)

Same pattern for erp_mirror_cust_shipto joins — add cs.system_id = soh.system_id.

IMPORTANT: Both PostgreSQL AND SQL Server code paths must be updated.
The SQL Server path uses positional ? params. The PostgreSQL path uses
named :params. See CLAUDE.md "Dual-database parity" for details.

**2. Fix item_branch join in customers.py (~line 23)**

The get_sales_products query joins erp_mirror_item_branch without system_id.
Add system_id to the join condition and add is_deleted = false.

**3. Add system_id to COUNT query in orders.py (~line 375)**

The handling code breakdown query filters by so_id but not system_id.
Add system_id filter to the WHERE clause.

**4. Verify all queries have is_deleted = false**

Run: grep -n 'erp_mirror_' app/Services/erp/*.py | grep -v 'is_deleted'
Fix any queries that directly read mirror tables without is_deleted = false.

### Testing

No formal test suite exists. Verify with:
  DATABASE_URL=sqlite:///test.db python -c "from app import create_app; app = create_app(); print('OK')"

### Commit and push when done. Do NOT create a PR unless asked.
```

## Agent Prompt for Phase 2 (TypeScript Port)

```
You are working on the LiveEdge repository (amcgrean/liveedge), a TypeScript
app that replaces the Python/Flask WH-Tracker (amcgrean/WH-Tracker).

## Context

LiveEdge reads from the agility-api Supabase database — a live ERP mirror.
The Python codebase in WH-Tracker contains the reference SQL queries for all
ERP data access, organized as domain mixins in app/Services/erp/:

- base.py — infrastructure (not needed in TS, Supabase client replaces it)
- picks.py — open picks, counts, handling breakdown
- work_orders.py — work orders by barcode, open WO list
- orders.py — SO summary, order board, SO header/detail
- dispatch.py — dispatch stops, enrichment, shipment lines
- delivery.py — delivery tracker, KPIs, historical stats
- sales.py — hub metrics, order status, transactions, invoice lookup
- customers.py — customer search, details, products, salespeople

## Supabase Query Rules

1. Always filter by system_id first (partition key for all indexes)
2. Use matviews for dashboard/list data:
   - app_mv_open_picks_by_branch, app_mv_handling_by_branch
   - app_mv_shipment_status_by_so, app_mv_board_open_orders
   - app_po_header (matview, refreshed hourly)
3. Use RPCs: get_board_open_orders({ p_system_id }), get_po_detail()
4. Always include is_deleted = false on direct mirror reads
5. Join so_detail + item_branch on (system_id, item_ptr) together
6. No SELECT *, no unbounded COUNT(*), no new indexes

## Key tables

- erp_mirror_so_header — sales orders (system_id, so_id, so_status, sale_type, expect_date, cust_key)
- erp_mirror_so_detail — SO line items (system_id, so_id, sequence, item_ptr, qty_ordered)
- erp_mirror_item_branch — item per branch (system_id, item_ptr, handling_code)
- erp_mirror_shipments_header — shipments (system_id, so_id, ship_date, status_flag)
- erp_mirror_cust — customers (system_id, cust_key, cust_name)
- erp_mirror_cust_shipto — ship-to addresses (system_id, cust_key, seq_num)
- erp_mirror_wo_header — work orders (system_id, wo_id, wo_status, source_id)

## What NOT to port

- SQL Server fallback paths (LiveEdge is cloud-only)
- Legacy pyodbc connection code
- The _mirror_query/cache infrastructure (use Supabase client instead)
- is_deleted filtering (matviews handle it; add manually on direct queries)
```

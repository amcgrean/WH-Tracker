# Next Agent Handoff — 2026-03-31 (Purchasing Module)

## Objective

Continue building the purchasing module in `WH-Tracker`, but align it to the **real live Supabase purchasing mirror** rather than the earlier idealized schema.

This handoff assumes the Supabase DB will be seeded by the time implementation work resumes.

Primary source of truth for live assumptions:

- [PURCHASING_LIVE_DB_PLAN.md](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/docs/PURCHASING_LIVE_DB_PLAN.md)

## What Already Exists In Code

A first-pass purchasing scaffold has already been added:

- [app/Routes/purchasing.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Routes/purchasing.py)
- [app/Services/purchasing_service.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Services/purchasing_service.py)
- [app/templates/purchasing/manager_dashboard.html](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/templates/purchasing/manager_dashboard.html)
- [app/templates/purchasing/buyer_dashboard.html](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/templates/purchasing/buyer_dashboard.html)
- [app/templates/purchasing/po_workspace.html](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/templates/purchasing/po_workspace.html)
- [app/templates/purchasing/suggested_buys.html](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/templates/purchasing/suggested_buys.html)
- [app/auth.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/auth.py) now includes purchasing permission helpers
- [app/navigation.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/navigation.py) has new purchasing entries
- [app/templates/workcenter.html](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/templates/workcenter.html) links into the new module

There is also a first-pass migration:

- [migrations/versions/purchasing_workbench.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/migrations/versions/purchasing_workbench.py)

## Important Reality Check

The scaffold is useful, but it is **not yet fully aligned** to the live purchasing DB plan.

The next agent should treat the current code as a starting point, not as final architecture.

### Main mismatches still to fix

1. Some app-owned purchasing models currently use `branch_code` naming.
   - Live purchasing branch scope should be treated as `system_id`.
   - App-owned tables can still store the ERP branch value, but the preferred direction is to rename future app-owned purchasing columns and contracts to `system_id`.

2. [app/Models/models.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Models/models.py) currently contains several proposed ERP purchasing mirror ORM classes.
   - These are acceptable as read-only ORM declarations **only if they match the seeded Supabase tables exactly**.
   - Do **not** let Flask migrations try to own or create ERP mirror tables.

3. [migrations/versions/purchasing_workbench.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/migrations/versions/purchasing_workbench.py) currently creates app-owned workflow tables and extends `po_submissions`, which is good.
   - But before running it against the real environment, confirm naming should use `system_id` rather than `branch_code` in those app-owned tables.
   - If you change that, create a replacement migration rather than editing production history after deployment.

4. The current service layer has already been partially corrected to degrade safely when PPO/supplier analytics are missing, but it still needs a final pass once the seeded DB is visible.

## Live DB Facts To Build Against

Use these current live tables now:

- `erp_mirror_po_header`
- `erp_mirror_po_detail`
- `erp_mirror_receiving_header`
- `erp_mirror_receiving_detail`
- `erp_mirror_item`
- `erp_mirror_item_branch`
- `erp_mirror_item_uomconv`
- `erp_mirror_wo_header`
- `app_po_header` materialized view
- `app_po_search` view
- `app_po_detail` view
- `app_po_receiving_summary` view
- `po_submissions`

Treat these as future or optional enrichments:

- `erp_mirror_item_supplier`
- `erp_mirror_supplier_dim`
- `erp_mirror_suppname`
- `erp_mirror_supp_ship_from`
- `erp_mirror_ppo_header`
- `erp_mirror_ppo_detail`
- `erp_mirror_purchase_type`
- `erp_mirror_purchase_costs`
- `erp_mirror_param_po`
- `erp_mirror_param_po_cost`
- `erp_mirror_receiving_status`

Critical rule:

- Branch scoping is `erp_mirror_po_header.system_id`

## What The Next Agent Should Do

### Priority 1 — Reconcile the current scaffold with the seeded Supabase schema

Inspect the real seeded columns for:

- `app_po_header`
- `app_po_search`
- `app_po_detail`
- `app_po_receiving_summary`
- `erp_mirror_po_header`
- `erp_mirror_po_detail`
- `erp_mirror_receiving_header`
- `erp_mirror_receiving_detail`
- `po_submissions`

Then adjust:

- [app/Services/purchasing_service.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Services/purchasing_service.py)
- [app/Models/models.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Models/models.py)
- [migrations/versions/purchasing_workbench.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/migrations/versions/purchasing_workbench.py)

Goals:

- no code should assume `branch_code` on live PO mirrors
- no code should assume non-live views like `app_supplier_performance`
- no code should assume PPO mirrors are populated enough for core behavior

### Priority 2 — Keep only app-owned workflow state under Flask migration ownership

The app should own:

- `purchasing_work_queue`
- `purchasing_assignments`
- `purchasing_notes`
- `purchasing_tasks`
- `purchasing_approvals`
- `purchasing_exception_events`
- `purchasing_dashboard_snapshots`
- `purchasing_activity_log` / `purchasing_activity`
- `po_submissions` extensions

The app should **not** own:

- ERP mirror tables
- Supabase-managed views/materialized views

### Priority 3 — Connect the dashboards to live DB-first behavior

Manager dashboard should work from:

- `app_po_search`
- `app_po_header`
- `app_po_receiving_summary`
- app-owned workflow tables
- `po_submissions`

Buyer workspace should work from:

- app-owned queue tables
- derived overdue PO items from `app_po_search`
- derived receiving review items from `po_submissions`

PO workspace should work from:

- `app_po_header`
- `app_po_detail`
- `app_po_receiving_summary`
- `po_submissions`
- app-owned notes/tasks/approvals/exceptions/activity

### Priority 4 — Keep degraded behavior explicit until future mirrors are real

Until seeded and validated, the UI/API should intentionally degrade:

- Suggested buys:
  - empty state or limited preview
  - no fake inferred data

- Supplier watchlist:
  - derive from overdue open POs only
  - no OTIF or lead-variance scorecards yet

- Supplier details:
  - show only fields present in current PO views
  - defer ship-from city/state/contact enrichment

- Receiving state:
  - infer from current receiving rows plus app exceptions
  - do not imply `receiving_status` is connected

### Priority 5 — Decide on app-owned purchasing column naming

Recommended:

- new app-owned tables should use `system_id`

If current migration already created `branch_code` in a local environment, do not panic.
For production-safe rollout:

- if not yet deployed, rename before rollout
- if already deployed, add a compatibility migration rather than hard-breaking

## Suggested Build Order

1. Validate real seeded schema and compare to [PURCHASING_LIVE_DB_PLAN.md](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/docs/PURCHASING_LIVE_DB_PLAN.md)
2. Fix the ORM/migration naming and ownership boundaries
3. Update purchasing service queries to exact live columns
4. Add or adjust app-owned workflow migrations if needed
5. Verify manager dashboard against real data
6. Verify buyer queue against real data
7. Verify PO workspace against real data
8. Only then turn on PPO-backed suggested buys if those mirrors are truly seeded and usable

## Known Local Verification Status

Completed already:

- Python compile checks passed for the purchasing service/routes
- Jinja parse checks passed for the purchasing templates

Known local limitation:

- Full app boot in this shell was blocked by a missing local package install despite `requirements.txt` including it
- Do not treat that as a purchasing blocker; validate in the real app environment once dependencies are installed

## Files To Review First

Read these first before changing anything:

- [docs/PURCHASING_LIVE_DB_PLAN.md](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/docs/PURCHASING_LIVE_DB_PLAN.md)
- [app/Services/purchasing_service.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Services/purchasing_service.py)
- [app/Routes/purchasing.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Routes/purchasing.py)
- [app/Models/models.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Models/models.py)
- [migrations/versions/purchasing_workbench.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/migrations/versions/purchasing_workbench.py)
- [app/Services/po_service.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Services/po_service.py)
- [app/Routes/po_routes.py](C:/Users/amcgrean/python/wh-tracker-fly/WH-Tracker/app/Routes/po_routes.py)

## One-Line Mission For The Next Agent

Take the existing purchasing scaffold, strip out any idealized-schema assumptions, and finish Phase 1 against the real `system_id`-scoped Supabase purchasing mirrors and current PO materialized/view layer.

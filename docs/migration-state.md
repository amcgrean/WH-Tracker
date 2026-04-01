# Migration State — WH-Tracker (as of 2026-04-01)

This document records the Alembic migration state at the time of the
beisser-takeoff merge preparation, so that Drizzle-managed tables can be
safely restored into the `bids` schema without conflicting with the Flask app.

## Alembic heads

The migration chain has a single head:

```
Current head: t3u4v5w6x7y8  (add_estimating_user_id — 2026-04-01)
```

Full linear chain (oldest → newest):

```
3e6c5d3f8ce5  initial_migration
2b3fda096311  add_user_type_to_pickster
83fabbe397a1  add_pickassignment_table
a1c4e2f9b803  add_credit_images_table
  ↳ branches (d1e2f3a4b5c6, f3a8b9c4d5e6) merged at b4c5d6e7f8a9
c9d8e7f6a5b4  add_audit_trail
d1e2f3a4b5c6  add_customer_notes_table
f3a8b9c4d5e6  add_normalized_erp_mirror_tables
a8f3c2d1e9b7  add_gps_coords_to_cust_shipto
b4c5d6e7f8a9  merge_customer_notes_and_mirror_heads
e1f2a3b4c5d6  add_sales_perf_indexes
f9a1b2c3d4e5  add_mirror_perf_indexes_v2
a7b8c9d0e1f2  add_trgm_search_indexes
a2b3c4d5e6f7  add_wo_assignments_table
g1h2i3j4k5l6  add_shipment_num_to_pick
h2i3j4k5l6m7  merge_shipment_num_head  (merges c1d2e3f4a5b6 + g1h2i3j4k5l6)
c1d2e3f4a5b6  merge_three_heads        (merges a7b8c9d0e1f2 + a2b3c4d5e6f7 + a8f3c2d1e9b7)
d2e3f4a5b6c7  add_order_writer_to_so_header
i3j4k5l6m7n8  add_auth_tables          (AppUser, OTPCode)
j4k5l6m7n8o9  add_branch_code_to_pick_tables
k5l6m7n8o9p0  merge_order_writer_and_branch_code
k5l6m7n8o9p0b add_branch_to_app_users
l6m7n8o9p0q1  create_po_submissions
m7n8o9p0q1r2  add_dispatch_planning_tables
n8o9p0q1r2s3  add_dashboard_stats_table
o9p0q1r2s3t4  dashboard_stats_per_branch
p1q2r3s4t5u6  add_purchasing_workbench_tables
r1s2t3u4v5w6  rename_purchasing_branch_scope_to_system_id
s2t3u4v5w6x7  fix_item_supplier_unique_key   (no-op — Pi-managed table)
t3u4v5w6x7y8  add_estimating_user_id         ← CURRENT HEAD
```

## app_users role values (documented)

`app_users.roles` is a JSON array of strings.  Roles in active use:

| Role         | Who has it                                      |
|--------------|-------------------------------------------------|
| `admin`      | System administrators (bypasses all role checks)|
| `ops`        | Operations staff                                |
| `sales`      | Sales representatives / order writers           |
| `picker`     | Warehouse pickers (kiosk users)                 |
| `supervisor` | Floor supervisors                               |
| `warehouse`  | Warehouse workers (non-picker)                  |
| `production` | Production / work order workers                 |
| `purchasing` | Buyers                                          |
| `manager`    | Branch / department managers                    |
| `delivery`   | Delivery drivers                                |
| `dispatch`   | Dispatch coordinators                           |
| `credits`    | RMA / credit image reviewers                    |
| `estimator`  | **NEW** — beisser-takeoff bid management access |
| `designer`   | **NEW** — beisser-takeoff design tools access   |

There is no database-level enum or code-level whitelist for role strings — they
are stored as free-text JSON and compared with `has_role()` / `_is_allowed()`.
Adding a new role requires no schema or code change beyond assigning it to a
user and gating routes/nav items with it.

## Tables in the public schema (Flask-managed)

These tables live in the PostgreSQL `public` schema and are managed by Flask
Alembic migrations.  The beisser-takeoff Drizzle tables **must not** use the
`public` schema — use the `bids` schema instead.

### App tables

| Table                         | Description                                      |
|-------------------------------|--------------------------------------------------|
| `app_users`                   | Authenticated users (OTP login, roles, branch)   |
| `otp_codes`                   | One-time login codes                             |
| `pickster`                    | Warehouse pickers (kiosk identity)               |
| `pick`                        | Completed pick records                           |
| `PickTypes`                   | Pick type definitions                            |
| `pick_assignments`            | SO→picker assignment                             |
| `wo_assignments`              | Work order builder assignments                   |
| `audit_events`                | Operational audit trail                          |
| `dashboard_stats`             | Pre-computed dashboard counters (single row)     |
| `customer_notes`              | Sales rep call log / CRM notes                   |
| `credit_images`               | RMA credit photo uploads                         |
| `po_submissions`              | PO check-in photo submissions                    |
| `files`                       | Polymorphic file attachments (R2-backed)         |
| `file_versions`               | File version history                             |

### Dispatch tables

| Table                         | Description                                      |
|-------------------------------|--------------------------------------------------|
| `dispatch_routes`             | Planned delivery routes                          |
| `dispatch_route_stops`        | Individual stops on a route                      |
| `dispatch_drivers`            | Driver records                                   |
| `dispatch_truck_assignments`  | Truck-to-route assignments                       |

### Purchasing tables

| Table                              | Description                               |
|------------------------------------|-------------------------------------------|
| `purchasing_assignments`           | Buyer–supplier/PO assignments             |
| `purchasing_work_queue`            | Buyer task queue                          |
| `purchasing_notes`                 | PO / entity notes                         |
| `purchasing_tasks`                 | Individual purchasing tasks               |
| `purchasing_approvals`             | Approval workflow records                 |
| `purchasing_exception_events`      | Exception handling events                 |
| `purchasing_dashboard_snapshots`   | Point-in-time dashboard snapshots         |
| `purchasing_activity`              | Purchasing audit trail                    |

### ERP mirror tables (Pi sync worker — read-only in Flask)

| Table                              | Description                               |
|------------------------------------|-------------------------------------------|
| `erp_mirror_so_header`             | Sales order headers                       |
| `erp_mirror_so_detail`             | Sales order line items                    |
| `erp_mirror_cust`                  | Customer master                           |
| `erp_mirror_cust_shipto`           | Customer ship-to addresses                |
| `erp_mirror_shipments_header`      | Shipment / invoice headers                |
| `erp_mirror_shipments_detail`      | Shipment line items                       |
| `erp_mirror_wo_header`             | Work order headers                        |
| `erp_mirror_pick_header`           | Pick headers (normalized)                 |
| `erp_mirror_pick_detail`           | Pick detail lines (normalized)            |
| `erp_mirror_print_transaction`     | Print transaction records                 |
| `erp_mirror_print_transaction_detail` | Print transaction detail lines        |
| `erp_mirror_item`                  | Item / product master                     |
| `erp_mirror_item_branch`           | Per-branch item data                      |
| `erp_mirror_item_supplier`         | Item–supplier relationships               |
| `erp_mirror_item_uom_conv`         | Unit-of-measure conversions               |
| `erp_mirror_supplier`              | Supplier master                           |
| `erp_mirror_ar_open`               | A/R open balances                         |
| `erp_mirror_ar_open_detail`        | A/R open balance detail                   |
| `erp_mirror_purchase_order_header` | Purchase order headers                    |
| `erp_mirror_purchase_order_detail` | Purchase order line items                 |
| `erp_mirror_receiving_header`      | Receiving headers                         |
| `erp_mirror_receiving_detail`      | Receiving line items                      |
| `erp_mirror_receiving_status`      | Receiving status codes                    |
| `erp_mirror_suggested_po_header`   | Suggested PO headers                      |
| `erp_mirror_suggested_po_detail`   | Suggested PO line items                   |
| `erp_mirror_purchase_cost`         | Purchase cost records                     |
| `erp_mirror_purchase_type`         | Purchase type codes                       |
| `erp_mirror_purchasing_parameter`  | Purchasing parameters                     |
| `erp_mirror_purchasing_cost_parameter` | Purchasing cost parameters            |
| `erp_sync_state`                   | Pi sync worker heartbeat                  |
| `erp_sync_batch`                   | Sync batch log                            |
| `erp_sync_table_state`             | Per-table sync state                      |

### Alembic internal

| Table              | Description                       |
|--------------------|-----------------------------------|
| `alembic_version`  | Tracks current migration revision |

## Schema recommendation for beisser-takeoff (Drizzle)

Use schema `bids` for all beisser-takeoff tables to avoid any collision with
the above.  Create it once with:

```sql
CREATE SCHEMA IF NOT EXISTS bids;
```

Then configure Drizzle with `schema: 'bids'` in your table definitions.  The
legacy read-only tables (`bid`, `customer`, `user`, `design`, etc.) should also
be migrated into `bids` to keep them separate from the Flask `public` schema.

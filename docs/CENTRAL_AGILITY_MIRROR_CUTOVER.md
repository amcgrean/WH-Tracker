# Central Agility Mirror + ToolBx Cutover

Last updated: 2026-03-24

## 2026-03-24 Cloud-Only Runtime Contract (WH-Tracker)

WH-Tracker now operates as a cloud database app by default:

- `DATABASE_URL` is the required primary connection.
- ERP-backed reads come from normalized mirror tables in that cloud Postgres database.
- Tracker-owned workflow data (`pick`, `pickster`, `pick_assignments`, `audit_events`, work-order assignment state, notes, uploads metadata) is written by WH-Tracker to the same cloud Postgres database.
- Direct SQL Server access is now a break-glass fallback only (`ENABLE_LEGACY_ERP_FALLBACK=true`) and is disabled by default.

Dispatch and delivery GPS behavior is now mirror-driven:

- WH-Tracker consumes `erp_mirror_cust_shipto.lat` / `lon` / `geocode_source`.
- In-app geocoding endpoint `/api/geocode-pending` is deprecated and returns HTTP `410`.
- Geocoding responsibility is upstream in `beisser-api` mirror sync.

## Ownership

### `tracker` / `agility-api`

- runs on the on-prem Raspberry Pi
- reads Agility SQL Server locally
- writes normalized ERP mirror tables into Supabase Postgres
- owns sync metadata, worker heartbeat, batch history, and deployment/runtime docs

### `ToolBxAPI`

- owns ToolBx-specific exports, PDF/document handling, bulk upload flow, and SFTP behavior
- reads from the shared Postgres mirror by default through a source abstraction
- keeps a temporary SQL Server fallback only for jobs during the cutover phase

## Shared Mirror Contract

The shared cloud mirror is the only downstream ERP source for:

- WH-Tracker
- PO-Pics / receiving
- ToolBx
- bids
- BI

The mirror stays ERP-like and normalized. App workflow state remains in app-owned tables.

## First Vertical Slice

Initial mirrored tables:

- `cust`
- `cust_shipto`
- `item`
- `item_branch`
- `item_uomconv`
- `so_header`
- `so_detail`
- `shipments_header`
- `shipments_detail`
- `wo_header`
- `pick_header`
- `pick_detail`
- `po_header`
- `po_detail`
- `receiving_header`
- `receiving_detail`
- `aropen`
- `aropendt`
- `print_transaction`
- `print_transaction_detail`

AR/document definitions exist, but AR/document loading remains intentionally paused because of current Supabase storage pressure.

Each mirrored table carries:

- natural ERP keys where practical
- `source_updated_at`
- `synced_at`
- `sync_batch_id`
- `row_fingerprint`
- `is_deleted`

Worker/system tables:

- `erp_sync_state`
- `erp_sync_batches`
- `erp_sync_table_state`

## Sync Strategy

### Master / reference tables

- examples: `cust`, `cust_shipto`, `item`, `item_branch`, `item_uomconv`
- cadence: periodic incremental sync
- fallback: replace-style refresh when source timestamps are weak

### Operational tables

- examples: `so_header`, `so_detail`, `shipments_header`, `shipments_detail`, `pick_header`, `pick_detail`, `wo_header`
- cadence: near-real-time polling with a 3-5 second target where practical
- fallback: rolling reconciliation windows + periodic full merge

### AR / document tables

- examples: `aropen`, `aropendt`, `print_transaction`, `print_transaction_detail`
- cadence: incremental windows keyed by update timestamps or date slices
- fallback: periodic reconciliation/full refresh to catch late changes and deletes

## Runtime Notes

- credentials stay fully env-driven
- SQL Server is read-only from the Pi worker
- Supabase/Postgres is write-only for the mirror worker
- mirror reads from apps never require local ERP network access
- for serverless deployments, Postgres should use a pooled connection endpoint and serverless-safe SQLAlchemy engine options
- Pi steady state is:
  - continuous worker on `--family operational`
  - separate master sync timer
  - AR/doc paused

## WH-Tracker Cutover Status

Sales pages now read through `ERPService` against the shared central mirror for:

- `/sales/hub`
- `/sales/order-status`
- `/sales/invoice-lookup`
- `/sales/products`
- `/sales/customer-profile/<customer_number>`
- `/sales/customer-notes/<customer_number>`
- `/sales/order-history`
- `/sales/reports`

Supervisor/work-order pages remain app-owned for assignment state, but their ERP reads now tolerate the current central mirror data shape:

- `/supervisor/dashboard`
- `/supervisor/work_orders`
- `/work_orders`
- `/work_orders/open/<user_id>`
- `/work_orders/scan/<user_id>`
- `/work_orders/select`

Work-order queue creation now preserves the real sales order number from the selection step instead of writing placeholder SO values into local assignment records.

The legacy `/erp-cloud-sync` endpoint has been retired. Tracker now reads from the normalized mirror through `CENTRAL_DB_URL`, and the old API ingest path should not be used.

## Verification

Focused route smoke coverage now lives in:

- `verify_route_smoke.py`

Run it with the project venv:

- `.\venv\Scripts\python.exe .\verify_route_smoke.py`

The script stands up a temporary SQLite app DB, mocks ERP service responses, and verifies the key sales, work-order, and supervisor routes render and post without relying on live ERP connectivity.

## Deployment Capacity Notes

For `tracker` on Vercel or any other serverless platform:

- use a pooled Postgres connection string, not a direct raw Postgres host, for `DATABASE_URL`
- keep `DB_USE_NULL_POOL=true` unless you have a non-serverless runtime with controlled worker counts
- use the same guidance for `CENTRAL_DB_URL` if central-mirror reads are enabled from the app runtime

That setup is the minimum needed to avoid connection-count spikes when many concurrent requests cold-start at once. The app code is now configured to honor those engine settings, but the database endpoint itself still needs to be the pooled variant in production.

## Tracker App DB Cutover

Tracker can now run with both:

- `DATABASE_URL` pointing at Supabase for app-owned tables like `pickster`, `pick`, `work_orders`, and `customer_notes`
- `CENTRAL_DB_URL` pointing at the same Supabase database for normalized ERP mirror reads

For local cutover support, `migrate_tracker_tables_to_supabase.py` copies the core Tracker-owned tables from the old database into Supabase.

By default it migrates the app-owned tables needed for live Tracker behavior. The old legacy cache tables (`erp_mirror_picks`, `erp_mirror_work_orders`, `erp_delivery_kpis`) are left out unless `INCLUDE_LEGACY_MIRROR_TABLES` is explicitly set, because the app should now prefer normalized mirror reads from Supabase instead of depending on the older cache tables.

As of 2026-03-19, that smoke path also validates the current Alembic chain on SQLite, including:

- the normalized ERP mirror migration branch
- the customer notes branch
- the merge migration that reunifies those heads
- the audit trail migration in SQLite-safe batch mode

This keeps local and CI-style boot checks from passing the routes while silently leaving the migration graph in a branched or partially applied state.

## Current Cleanup Boundary

Safe to keep:

- central-mirror read helpers in `ERPService`
- work-order and supervisor local assignment state
- legacy fallback branches while non-central deployments still exist

Not yet removed on purpose:

- old `ERPMirrorPick` / `ERPMirrorWorkOrder` fallback code paths inside `ERPService`
- retired legacy `/erp-cloud-sync` ingestion route
- AR/document sync activation

Recommended next cleanup happens only after confirming no deployment still depends on the old ingest/fallback path.

## ToolBx Cutover Notes

`ToolBxAPI` now targets these shared contracts:

- `get_accounts_export_rows()`
- `get_ar_detail_export_rows()`
- `find_invoice_document(ref_num)`
- `find_statement_document(account_number, statement_date)`
- `get_jobs_export_rows()`

`PostgresMirrorSource` is the default path.

`LegacySqlServerSource` remains temporarily for:

- jobs fallback
- operational parity checks during migration

## Remaining Risks

- stored procedures may still hide business rules not visible in output files alone
- some ERP tables may not have reliable change timestamps
- document metadata/file linkage may need one more schema pass after first mirror validation
- 3-5 second sync is realistic for only the hottest table families at first
- serverless startup still logs a migration error when the configured Postgres target is unreachable; import continues, but live deployment validation should still be done against reachable DB credentials

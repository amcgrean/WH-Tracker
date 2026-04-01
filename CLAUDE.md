# CLAUDE.md - Agent Development Notes

## Project Overview

WH-Tracker (being rebranded to **LiveEdge**) is a Flask warehouse operations platform covering pick/pack, dispatch, sales order tracking, file storage, and ERP integration. Python 3.11, PostgreSQL primary DB, optional SQL Server ERP fallback. Deployed on **Fly.io** (Vercel project has been deleted).

## Quick Reference

```bash
# Run locally
python run.py

# Production
gunicorn run:app --bind 0.0.0.0:8080

# Database migrations
flask db upgrade
flask db migrate -m "description"
```

No formal test suite — test scripts are ad-hoc (`test_*.py` in root).

## Architecture

### App Structure

```
app/
  Routes/              # Flask Blueprints (each is a package or module)
    main/              # Pick/pack, work orders, admin (split into sub-modules)
    sales/             # Sales orders, transactions, customer workspace
    dispatch/          # Delivery tracking, route management
    auth/              # Passwordless OTP login
    files.py           # File upload/download via R2
  Services/            # Business logic
    erp_service.py     # Core ERP layer (~145KB)
    storage_service.py # Cloudflare R2 client (S3-compatible via boto3)
  Models/models.py     # All SQLAlchemy models
  templates/           # Jinja2 (base.html has blocks: title, head, content, scripts, navbar)
  static/              # CSS (style.css has design system), JS, icons
```

### Blueprints

| Blueprint | Prefix | Module | Purpose |
|-----------|--------|--------|---------|
| `main_bp` | `/` | `Routes.main` | Picks, picksters, work orders, admin |
| `sales_bp` | `/sales` | `Routes.sales` | Sales orders, transactions, customer workspace |
| `dispatch_bp` | `/dispatch` | `Routes.dispatch` | Delivery tracking, route management |
| `auth_bp` | `/auth` | `Routes.auth` | Passwordless OTP login |
| `files` | `/files` | `Routes.files` | File upload/download/list via R2 |

### Database Architecture

- **Dual-database**: PostgreSQL (app + ERP mirror) with optional SQL Server fallback
- `central_db_mode` (bool on ERPService): When true, queries PostgreSQL mirror tables (`erp_mirror_*`). When false, queries SQL Server directly.
- **Both code paths must be kept in sync** when modifying ERP queries. The PostgreSQL path uses named params (`:param`), SQL Server uses positional (`?`).
- Mirror tables: `erp_mirror_so_header`, `erp_mirror_so_detail`, `erp_mirror_cust`, `erp_mirror_cust_shipto`, `erp_mirror_shipments_header`, `erp_mirror_shipments_detail`, etc.

### Dashboard Stats (Pre-computed Counts)

The `dashboard_stats` table holds **one row per branch** (`system_id` TEXT PRIMARY KEY) with pre-computed dashboard counts, so the homepage avoids heavy multi-join ERP queries. Updated by the **Pi sync worker** (`sync_erp.py`) each cycle via `ON CONFLICT (system_id) DO UPDATE`.

| Column | Type | Description |
|--------|------|-------------|
| `system_id` | text PK | Branch code e.g. `20GR`, `25BW`, `40CV`, `10FD` |
| `open_picks` | int | Distinct open SO count for this branch |
| `handling_breakdown_json` | text | JSON dict of distinct SO counts per handling code, e.g. `{"DOOR1": 5, "EWP": 3, "UNROUTED": 42}` |
| `open_work_orders` | int | Open WO count for this branch |
| `updated_at` | datetime | Last update timestamp |

**`UNROUTED`** is the key used for picks with no handling code assigned (not an em-dash).

**Dashboard route** (`picks.py:_read_dashboard_stats(branch)`) accepts a branch filter, queries the relevant row(s), and aggregates. `DSM` is treated as `20GR + 25BW` combined. Falls back to live ERP queries if any row is missing or stale (>5 minutes).

**`open_work_orders` is currently 0 for all branches** — `wo_header.branch_code` was recently added to the sync and existing rows backfill as they are touched in ERP. Do not rely on per-branch WO counts yet.

**Important**: When adding new dashboard stats, update three places:
1. `DashboardStats` model in `models.py`
2. `_update_dashboard_stats()` in `sync_erp.py` (Pi-side computation — groups by system_id, upserts per branch)
3. `_read_dashboard_stats()` in `picks.py` (web-side read + aggregation + fallback)

### Key ERP Data Model

**Sales Order Header** (`erp_mirror_so_header`):
- `so_id` — Sales order number
- `so_status` — O=Open, I=Invoiced, C=Closed, H=Hold
- `sale_type` — CM=Credit Memo, WillCall, Direct, XInstall, Hold (anything else = delivery/add-on)
- `salesperson` — Maps to Agility `sales_agent_1` (account rep)
- `order_writer` — Maps to Agility `sales_agent_3` (order writer)
- `expect_date` — Expected delivery date (primary date for sales order filtering)
- `system_id` — Branch identifier (20GR, 25BW, 40CV, 10FD)
- `cust_key`, `shipto_seq_num` — Customer/ship-to linkage

**Shipments Header** (`erp_mirror_shipments_header`):
- `ship_date` — When order shipped
- `invoice_date` — When invoice was generated
- `status_flag_delivery` — Delivery status
- Join to SO header on `(system_id, so_id)`

**User Model** (`AppUser`):
- `user_id` — ERP rep ID (e.g. "mschmit"), stored in session as `user_rep_id`
- `roles` — JSON array: `admin`, `ops`, `sales`, `picker`, `supervisor`
- Sales users see only their orders by default; admin/ops see all unless `?my_orders=1`

### Branch System

Branches: 20GR (Grimes), 25BW (Birchwood), 40CV (Coralville), 10FD (Fort Dodge), DSM (Des Moines = 20GR+25BW).
Branch filter: URL param > session `selected_branch` > all. Normalized via `branch_utils.py`.

## Sales Transactions Page

The `/sales/transactions` page has two modes:

1. **Quick View Cards** — Preset views accessible via `?view=<name>`:
   - `my_open_3d` / `my_open_7d` — User's open orders by expect_date window
   - `branch_delivery` — Branch open orders excluding WillCall/Direct/CM
   - `branch_willcall` — Branch open orders, sale_type=WillCall only
   - `my_rma` — User's open credit memos (sale_type=CM, no date filter)
   - `my_shipped_2d` — User's orders by shipments_header.ship_date (last 2 days)
   - `my_invoiced_5d` — User's orders by shipments_header.invoice_date (last 5 days)

2. **Custom Search** — Manual filters (search, status, date range, salesperson, customer, ship-to)
   - Custom search bar is hidden when a Quick View card is active
   - Sales Agent dropdown: loads distinct `salesperson` values from `erp_mirror_so_header`
   - Customer dropdown: type-ahead search against `erp_mirror_cust` by name/code
   - Ship-To dropdown: appears after customer is selected, filterable by name/address/seq

"My" views filter where user is `salesperson` (agent_1) OR `order_writer` (agent_3).
Agent role dots on each row: green = Acct Rep, blue = Order Writer.

Delivery type filtering: exclude `('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD', 'CM')` — everything remaining is delivery/add-on. Always use uppercase when referencing sale types in code (`NON_DELIVERY_TYPES` constant in `sales_routes.py`).

### Sales Transactions API Endpoints
- `/sales/api/salespeople` — Distinct salesperson IDs (filtered by branch)
- `/sales/api/customers/list?q=` — Customer type-ahead (name/code search)
- `/sales/api/customers/shipto/<customer_code>` — Ship-to addresses for a customer
- `/sales/api/transactions` — JSON order data with all filters
- `/sales/api/customers/search?q=` — Customer search for global search bar

## File Storage (Cloudflare R2)

Files are stored in Cloudflare R2 (S3-compatible) via `StorageService` (`app/Services/storage_service.py`). Metadata is tracked in PostgreSQL via `File` and `FileVersion` models.

### Configuration (Fly secrets)
- `R2_ACCESS_KEY_ID` — R2 API access key
- `R2_SECRET_ACCESS_KEY` — R2 API secret key
- `R2_ENDPOINT_URL` — `https://<account_id>.r2.cloudflarestorage.com`
- `R2_BUCKET` — `liveedgefiles` (default)

### Models
- **`File`** — polymorphic attachment: `entity_type` + `entity_id` link to any parent (e.g. `work_order/123`, `po/456`). Tracks `original_filename`, `object_key`, `mime_type`, `size_bytes`, `uploaded_by`. Supports soft-delete (`is_deleted`).
- **`FileVersion`** — version history per file: `version_number`, `object_key`, `change_note`.

### R2 Object Key Format
`{entity_type}/{entity_id}/{timestamp}_{filename}` — built by `StorageService.build_object_key()`.

### Files Blueprint (`/files`)
- `POST /files/upload` — multipart upload, creates File + FileVersion
- `GET /files/<id>` — redirect to presigned R2 URL
- `GET /files/<id>/info` — JSON metadata with version history
- `DELETE /files/<id>` — soft-delete
- `GET /files/entity/<type>/<id>` — list files for an entity

### Usage Pattern
To attach files to a new entity type (e.g. purchase orders), just use `entity_type='po'` and `entity_id=<po_number>` — no schema changes needed.

## UI Design System

- **Glass cards**: `.glass-card` — semi-transparent with backdrop blur, 16px radius, hover lift
- **Buttons**: `.btn-ops-primary` — green gradient, `.btn-ops-gold` — gold gradient
- **Colors**: `--beisser-green: #004526`, `--beisser-gold: #c5a059`
- **Stat cards**: centered text, uppercase labels, large bold values
- **Animations**: `.animate-fade-in` with `.delay-1` through `.delay-3`
- Bootstrap 4 grid, Font Awesome 5 icons, Inter font

## Known Pitfalls & Review Checklist

### Pick/order counts: distinct SOs, not detail lines (CRITICAL)
When counting "open picks" or similar order-level metrics, always count **distinct (system_id, so_id)**, never `COUNT(*)` on `so_detail`. A single SO can have many line items — counting lines inflates the number and is much slower (requires detail table join). The `dashboard_stats` table and `get_open_picks_count()` both use `COUNT(DISTINCT ...)` for this reason.

### String column case sensitivity (CRITICAL)
ERP data stores text fields in mixed case (e.g. `sale_type` = `WillCall`/`Direct`/`XInstall`, `wo_status` = `Completed`/`Canceled`). **All** SQL filters comparing string columns must use `UPPER(COALESCE(..., ''))` on the column and uppercase literals:
```sql
-- CORRECT
UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
UPPER(COALESCE(soh.so_status, '')) = 'K'
UPPER(COALESCE(wh.wo_status, '')) NOT IN ('COMPLETED', 'CANCELED', 'C')

-- WRONG — will silently return wrong results
soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
soh.so_status = 'k'
wh.wo_status NOT IN ('Completed', 'Canceled')
```
This applies to: `sale_type`, `so_status`, `wo_status`, `tran_type`, `print_status`, `source`, and any other text column compared against literals.

For dynamic filters built from user input, always `.upper()` the Python values:
```python
valid_types = [t.strip().upper() for t in sale_type.split(',') if t.strip()]
```

For Python-side filtering of returned ERP data, normalize before comparing:
```python
# In _normalize_order_row(): so_status and sale_type are .upper()'d
open_orders = [r for r in rows if str(r.get('so_status', '')).upper() == 'O']
```

**Also applies to `dispatch_service.py`** — its `get_stops()` method has the same dual-filter pattern as `erp_service.py`.

### Dual-database parity
Every ERP query has two code paths (PostgreSQL + SQL Server). When adding or fixing filters, **both paths must be updated**. Use `replace_all` cautiously — the same logical fix may need different SQL syntax per database.

### Pagination link params
When adding new filter parameters to a route, **always update pagination links** in the template to include the new params, or they will be lost when the user clicks Next/Previous.

### Template variables
Every variable used in Jinja2 templates must be passed via `render_template()`. When adding new filter params, update both the route's render call and any pagination/navigation links in the template.

## Common Patterns

### Adding a new ERP query
1. Add method to `ERPService` in `erp_service.py`
2. Write the PostgreSQL path first (uses `self._mirror_query()` with named `:params`)
3. Add SQL Server fallback after `self._require_central_db_for_cloud_mode()` (uses `cursor.execute()` with `?` positional params)
4. Both paths must return the same dict structure
5. **Always use `UPPER(COALESCE(col, ''))` when comparing string columns** (`sale_type`, `so_status`, `wo_status`, `tran_type`, `print_status`, `source`) — see pitfalls above
6. When splitting user-provided filter strings, always `.upper()` the values: `[t.strip().upper() for t in param.split(',')]`
7. In `_normalize_order_row()`, string fields like `so_status` and `sale_type` are already `.upper()`'d — keep this convention for any new fields

### Route helper functions (`sales_routes.py`)
- `_get_branch()` — Reads branch from URL > session > all
- `_get_rep_id()` — Returns user's ERP rep ID (role-aware)
- `_normalize_order_row(row, rep_id='')` — Standardizes DB rows for templates, computes `agent_role`
- `_value(row, key, default)` — Safe dict/object accessor

### SO number normalization (CRITICAL for barcode scanning)
Barcode scanners encode SO numbers with leading zeros (e.g. `0001463004-001`) but ERP stores `so_id` without them (e.g. `1463004`). **All** routes that accept scanned barcodes must strip leading zeros via `normalize_so_number()` from `helpers.py` before storing or querying:
```python
from app.Routes.main.helpers import normalize_so_number

# normalize_so_number('0001463004') -> '1463004'
# normalize_so_number('0') -> '0'
barcode = normalize_so_number(parts[0].strip())
```
This is already applied to: smart scan API, manual pick input, start_pick, kiosk pick input, work order select (both standard and kiosk), and confirm_staged. **Any new route that accepts a scanned SO number must also call `normalize_so_number()`.**

The shipment sequence suffix (e.g. `-001`) is parsed separately and stored as-is in `Pick.shipment_num` — do not normalize it.

### Pick scanner workflow
1. Picker selects themselves on `/pick_tracker` (picker selector grid)
2. `/confirm_picker/<picker_id>` shows incomplete picks + Smart Scan input
3. Smart Scan (`/api/smart_scan`) auto-detects pick type from ERP:
   - Existing incomplete pick with same barcode -> completes it
   - ERP sale_type=WILLCALL -> auto-completed will call pick
   - Otherwise -> maps handling_code to pick type, starts timed pick
4. After successful scan, a "Done" button appears with 5-second countdown
5. Countdown auto-navigates back to picker selector; clicking Done skips the wait

## Deployment

- **Fly.io** (primary) — auto-runs migrations on startup (`RUN_MIGRATIONS_ON_START` defaults to `True` on Fly)
- **Auth is enforced** — `AUTH_REQUIRED=true` is set as a Fly secret; `enforce_auth` in `app/__init__.py` gates all routes globally. Per-blueprint `before_request` guards on `main_bp`, `dispatch_bp`, and `sales_bp` act as a second layer.
- **Exempt paths** — kiosk (`/kiosk/*`), TV (`/tv/*`), picker flow (`/pick_tracker`, `/confirm_picker/*`, `/input_pick/*`, `/complete_pick/*`, `/start_pick/*`, `/api/smart_scan`), and auth endpoints are permanently unauthenticated.
- New users must be created via `/auth/users` (admin only) before they can log in.
- ERP sync worker runs separately (`SYNC_INTERVAL_SECONDS=5`)
- File storage via Cloudflare R2 (secrets set in Fly dashboard)

## Consolidation Roadmap

This app is the single operational platform. Other apps are being merged in:
- **po-app** (`amcgrean/po-app`, TypeScript) — Purchase order management. Next to be migrated. DB tables likely already exist since it shares the same Postgres. R2 storage already configured.
- **estimating-app** / **beisser-takeoff** — Estimating/takeoff tools. Future migration. Will need file attachments (R2 ready for this).
- **po-pics** (`amcgrean/po-pics`, TypeScript) — PO photo capture. Will fold into PO module.

The app is being rebranded from "WH-Tracker / Beisser Ops" to **LiveEdge** (separate effort in progress).

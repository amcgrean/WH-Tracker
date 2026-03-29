# CLAUDE.md - Agent Development Notes

## Project Overview

WH-Tracker (Beisser Ops) is a Flask warehouse operations platform covering pick/pack, dispatch, sales order tracking, and ERP integration. Python 3.11, PostgreSQL primary DB, optional SQL Server ERP fallback.

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
  Routes/           # Flask Blueprints (main, sales, dispatch, auth)
  Services/         # Business logic (erp_service.py is ~145KB, the core ERP layer)
  Models/models.py  # All SQLAlchemy models
  templates/        # Jinja2 (base.html has blocks: title, head, content, scripts, navbar)
  static/           # CSS (style.css has design system), JS, icons
```

### Blueprints

| Blueprint | Prefix | File | Purpose |
|-----------|--------|------|---------|
| `main` | `/` | `routes.py` | Picks, picksters, work orders, admin |
| `sales` | `/sales` | `sales_routes.py` | Sales orders, transactions, customer workspace |
| `dispatch` | `/dispatch` | `dispatch_routes.py` | Delivery tracking, route management |
| `auth` | `/auth` | `auth_routes.py` | Passwordless OTP login |

### Database Architecture

- **Dual-database**: PostgreSQL (app + ERP mirror) with optional SQL Server fallback
- `central_db_mode` (bool on ERPService): When true, queries PostgreSQL mirror tables (`erp_mirror_*`). When false, queries SQL Server directly.
- **Both code paths must be kept in sync** when modifying ERP queries. The PostgreSQL path uses named params (`:param`), SQL Server uses positional (`?`).
- Mirror tables: `erp_mirror_so_header`, `erp_mirror_so_detail`, `erp_mirror_cust`, `erp_mirror_cust_shipto`, `erp_mirror_shipments_header`, `erp_mirror_shipments_detail`, etc.

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

2. **Custom Search** — Manual filters (search, status, date range)

"My" views filter where user is `salesperson` (agent_1) OR `order_writer` (agent_3).
Agent role dots on each row: green = Acct Rep, blue = Order Writer.

Delivery type filtering: exclude `('Direct', 'WillCall', 'XInstall', 'Hold', 'CM')` — everything remaining is delivery/add-on.

## UI Design System

- **Glass cards**: `.glass-card` — semi-transparent with backdrop blur, 16px radius, hover lift
- **Buttons**: `.btn-ops-primary` — green gradient, `.btn-ops-gold` — gold gradient
- **Colors**: `--beisser-green: #004526`, `--beisser-gold: #c5a059`
- **Stat cards**: centered text, uppercase labels, large bold values
- **Animations**: `.animate-fade-in` with `.delay-1` through `.delay-3`
- Bootstrap 4 grid, Font Awesome 5 icons, Inter font

## Common Patterns

### Adding a new ERP query
1. Add method to `ERPService` in `erp_service.py`
2. Write the PostgreSQL path first (uses `self._mirror_query()` with named `:params`)
3. Add SQL Server fallback after `self._require_central_db_for_cloud_mode()` (uses `cursor.execute()` with `?` positional params)
4. Both paths must return the same dict structure

### Route helper functions (`sales_routes.py`)
- `_get_branch()` — Reads branch from URL > session > all
- `_get_rep_id()` — Returns user's ERP rep ID (role-aware)
- `_normalize_order_row(row, rep_id='')` — Standardizes DB rows for templates, computes `agent_role`
- `_value(row, key, default)` — Safe dict/object accessor

## Deployment

- **Vercel** (serverless) or **Fly.io** (VMs) or **Docker**
- Auth gated by `AUTH_REQUIRED` env var
- ERP sync worker runs separately (`SYNC_INTERVAL_SECONDS=5`)

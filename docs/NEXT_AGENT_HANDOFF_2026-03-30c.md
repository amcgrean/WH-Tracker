# Next Agent Handoff — 2026-03-30 (Session 3)

## Session Summary

This session completed the full Dispatch Console overhaul — rebuilding it from a basic order grid into a route planning command center with modular JS architecture, Samsara truck integration, and Agility API stubs for future integration.

---

## What Was Done This Session

### 1. New Database Models (`app/Models/dispatch_models.py`)

Four new local planning tables (NOT ERP mirrors):

| Model | Table | Purpose |
|-------|-------|---------|
| `DispatchRoute` | `dispatch_routes` | Named route for a date — container for ordered stops |
| `DispatchRouteStop` | `dispatch_route_stops` | Stop within a route, with sequence and status |
| `DispatchDriver` | `dispatch_drivers` | Local driver roster (name, phone, default truck) |
| `DispatchTruckAssignment` | `dispatch_truck_assignments` | Daily Samsara truck ↔ driver ↔ route mapping |

Migration: `m7n8o9p0q1r2` (chained after `l6m7n8o9p0q1`)

### 2. New API Endpoints (`app/Routes/dispatch/planning.py`)

Added to the dispatch package (follows main's refactored `app/Routes/dispatch/` structure):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/kpis` | GET | Daily KPI counts (stops, unassigned, routes, trucks) |
| `/api/stops/enriched` | GET | Stops with order_value, pick_status, credit, WOs |
| `/api/routes` | GET/POST | List/create routes |
| `/api/routes/<id>` | PUT/DELETE | Update/delete routes |
| `/api/routes/<id>/stops` | POST | Add stops to route |
| `/api/routes/<id>/stops/reorder` | PUT | Reorder stops |
| `/api/routes/<id>/stops/<stop_id>` | DELETE | Remove stop |
| `/api/drivers` | GET/POST | List/create drivers |
| `/api/drivers/<id>` | PUT | Update driver |
| `/api/drivers/seed-from-erp` | POST | Seed roster from ERP history |
| `/api/trucks` | GET | Samsara vehicles merged with assignments |
| `/api/trucks/assignments` | POST | Create/update truck assignment |
| `/api/trucks/assignments/<id>` | PUT | Update assignment |
| `/api/trucks/assignments/copy-previous` | POST | Copy yesterday's assignments |

Added to `app/Routes/dispatch/stops.py`:
- `GET /api/stops/enriched`
- `GET /api/customers/<cust_key>/summary`
- `GET /api/orders/<so_id>/timeline`
- `GET /api/orders/<so_id>/work-orders`

### 3. Service Layer Additions

**`app/Services/dispatch_service.py`** — added:
- `get_routes_for_date()`, `create_route()`, `update_route()`, `delete_route()`
- `add_stops_to_route()`, `reorder_stops()`, `remove_stop()`
- `get_drivers()`, `create_driver()`, `update_driver()`, `seed_drivers_from_erp()`
- `get_truck_assignments()`, `upsert_truck_assignment()`, `copy_previous_assignments()`
- `get_daily_kpis()`

**`app/Services/erp_service.py`** — added:
- `get_enriched_dispatch_stops()` — enriches base stops with value, credit, WOs, local route info
- `get_customer_ar_summary()` — AR aging buckets from `erp_mirror_aropen`
- `get_order_work_orders()` — WOs linked to an SO
- `get_order_timeline()` — audit events for an order

### 4. New Four-Zone Layout (`app/templates/dispatch/index.html`)

Complete rewrite from two-panel grid:
- **Command bar**: KPI tiles (Stops / Unassigned / Routes / Trucks Out), date/branch/search controls, truck panel toggle, settings, shortcuts button
- **Truck panel** (collapsible): Samsara truck table with driver/route dropdowns, Copy Yesterday, Seed Drivers
- **Route panel** (left 320px): Unassigned/Routes/All tabs, stop list with pick-status dots, route accordion cards with drag-drop
- **Map** (center, flex): Leaflet with color-coded stop markers by route, route polylines, vehicle overlay
- **Detail flyout** (right 420px, slides in): Status timeline stepper, order summary, line items, customer credit bar + AR aging, work orders, pick activity, action buttons

### 5. JS Module Architecture (`app/static/dispatch/`)

Replaced monolithic `demo.js` with 10 ES modules:

| File | Responsibility |
|------|---------------|
| `dispatch-app.js` | Main controller — boot, data loading, refresh loop, URL hash state |
| `dispatch-state.js` | State store + event bus (`on`/`emit`) |
| `dispatch-api.js` | All fetch calls centralized |
| `dispatch-command-bar.js` | KPI tiles, date/branch/search/toolbar |
| `dispatch-route-panel.js` | Stop list, route cards, drag-drop |
| `dispatch-map.js` | Leaflet markers, polylines, vehicle overlay |
| `dispatch-detail-panel.js` | Right flyout with all detail sections |
| `dispatch-trucks.js` | Truck assignment panel, driver dropdowns |
| `dispatch-keyboard.js` | Keyboard shortcuts |
| `dispatch-settings.js` | Settings modal (localStorage persistence) |

### 6. Branch/Merge Work

- Merged `origin/main` into `main-fly` — resolved 5 conflicts
- Restructured dispatch endpoints from monolithic `dispatch_routes.py` into the package layout that `main` introduced (`app/Routes/dispatch/stops.py`, `app/Routes/dispatch/planning.py`)
- Renamed migration to avoid revision ID collision with main's `j4k5l6m7n8o9`
- Pushed `main-fly` → `main` (fast-forward, clean)

---

## Current Production State

- **URL:** https://wh-tracker-fly.fly.dev
- **Branch:** `main` is now the live branch (same as `main-fly`)
- **Alembic head:** `m7n8o9p0q1r2` (needs `flask db upgrade` on next deploy)
- **Dispatch console:** `/dispatch/` — new four-zone layout deployed
- **Auth:** Email OTP (Resend as primary provider)

---

## What Needs To Happen Next

### Priority 1 — Deploy & Run Migration

```bash
fly deploy
fly ssh console --app wh-tracker-fly -C "flask db upgrade"
```

Verify 4 new tables exist: `dispatch_routes`, `dispatch_route_stops`, `dispatch_drivers`, `dispatch_truck_assignments`

### Priority 2 — Manual Dispatch Console Test

1. Load `/dispatch/` — four-zone layout should render
2. Set date + branch, click Load
3. Verify stop list populates (unassigned tab)
4. Create a route: "+ New Route"
5. Drag a stop onto the route card
6. Open truck panel — verify Samsara trucks appear
7. Click a stop — detail flyout should open with order info
8. Test keyboard shortcuts: `?`, `/`, `n`, `Esc`
9. Verify manifest PDF still works (select a stop, Ctrl+P or Print Manifest button)

### Priority 3 — Enriched Stops Data Quality

The `get_enriched_dispatch_stops()` adds JOINs for `order_value`, `credit_hold`, `has_work_orders`, `pick_status`. These JOINs assume specific `erp_mirror_*` table/column names — verify the pick_status dot colors are showing correctly and credit holds are flagging as expected.

### Priority 4 — Agility API Integration (when ready)

Action buttons in the detail flyout are stubbed and disabled:
- **Create Pick File** → `PickFileCreate`
- **Stage Shipment** → `DispatchHeaderCreate`
- **Mark Loaded** → `ShipmentInfoUpdate`
- **Update Status** → `ShippingStatusGet`
- **Record POD** → `PODSignatureCreate`

When API access is available, add a service layer method for each and connect the buttons.

### Priority 5 — PO Module Browser Test (deferred from prior session)

See `NEXT_AGENT_HANDOFF_2026-03-30b.md` — the PO data pipeline is working but needs manual browser verification of the full check-in wizard flow.

---

## Dispatch Console Architecture Notes

### Driver/Route Separation
Historical Agility data has `driver` = `route` (same field value e.g. "SMITH"). Our system models them separately — `DispatchRoute` is a named stop sequence, `DispatchDriver` is a person. The `DispatchTruckAssignment` table bridges the gap daily.

### Route Colors
10-color palette in `dispatch-route-panel.js` (`ROUTE_COLORS`) — imported by `dispatch-map.js` to color markers and polylines consistently.

### Event Bus Pattern
All modules communicate via `dispatch-state.js` events. Key events:
- `filters-changed` → reload all data
- `stops-loaded`, `routes-loaded` → update panels and map
- `stop-selected` → pan map, optionally open detail
- `detail-open` → open flyout with full data
- `routes-reload` → reload routes only (after mutations)
- `trucks-panel-opened` → lazy-load truck data

### URL Hash State
The app syncs `date` and `branch` to the URL hash (`#date=2026-03-30&branch=20GR`) for bookmarkable links.

---

## Key New Files

| File | Purpose |
|------|---------|
| `app/Models/dispatch_models.py` | 4 local planning models |
| `app/Routes/dispatch/planning.py` | Route/driver/truck/KPI endpoints |
| `app/static/dispatch/dispatch-app.js` | Main boot controller |
| `app/static/dispatch/dispatch-map.js` | Map module |
| `app/static/dispatch/dispatch-detail-panel.js` | Detail flyout |
| `app/static/dispatch/dispatch-trucks.js` | Truck panel |
| `app/static/dispatch/dispatch-keyboard.js` | Keyboard shortcuts |
| `app/static/dispatch/dispatch-settings.js` | Settings modal |
| `migrations/versions/m7n8o9p0q1r2_add_dispatch_planning_tables.py` | Migration |

## Architecture Rules (permanent, do not regress)

1. **TRIM joins** — `central_db_mode` queries joining on `cust_key` or `seq_num` must use `TRIM()`.
2. **No system_id on customer joins** — `erp_mirror_cust` / `erp_mirror_cust_shipto` are centralized. Never join on `system_id`.
3. **admin bypass** — `@role_required` and `_is_allowed()` both short-circuit for `admin`. Keep in sync.
4. **IF NOT EXISTS on migrations** — Use raw SQL with `IF NOT EXISTS` guards for any columns that may have been applied outside Alembic.
5. **R2 for uploads** — New upload flows use R2 via boto3. Never `UPLOAD_FOLDER` for new features.
6. **No Supabase client** — SQLAlchemy + psycopg2 only.
7. **UPPER(COALESCE()) for string comparisons** — ERP data is mixed case.
8. **expand_branch_filter()** — Never use `== branch` when branch could be `GRIMES_AREA`. It expands to `['20GR', '25BW']`.
9. **Dispatch routes in package** — New dispatch endpoints go in `app/Routes/dispatch/` (stops.py, planning.py, api.py). Do NOT create a new monolithic `dispatch_routes.py`.

## Fly.io Quick Commands

```bash
fly deploy
fly logs --app wh-tracker-fly --no-tail
fly ssh console --app wh-tracker-fly -C "flask db upgrade"
fly ssh console --app wh-tracker-fly -C "flask db current"
fly secrets list --app wh-tracker-fly
```

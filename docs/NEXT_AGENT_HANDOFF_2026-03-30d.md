# Next Agent Handoff — 2026-03-30 (Session 4)

## Session Summary

Session confirmed PO search performance work (materialized view) was already complete
from Session 3. This session focused on auth readiness: auditing the current state,
clarifying kiosk exemptions, and confirming the deploy is clean and ready to flip.

---

## What Was Done This Session

### 1. Confirmed PO Search Performance Already Done (Session 3)

`app_po_header` is a materialized view, `pg_cron` refreshes every 15 min, manual
refresh endpoint + button exist on the Open POs page. No new work needed.

### 2. Confirmed Admin User + User Management Ready

- `amcgrean@beisserlumber.com` (id=1, role=`admin`) has full access to all routes
  including `/auth/users` for adding/editing users
- Admin UI at `/auth/users` is the single source of truth for user creation
- Users must exist in `app_users` before they can log in (no self-registration)

### 3. Confirmed Kiosk / TV Routes Are Intentionally Unauthenticated

`/kiosk/<branch>/*` and `/tv/<branch>/*` are warehouse floor screens:
- Kiosk = shared branch tablets where pickers select themselves + input picks
- TV = branch wallboards showing open picks

These do NOT and should NOT require login. When applying `@login_required` to
main/sales/dispatch routes, **skip `kiosk.py` and `tv.py` entirely.**

### 4. Confirmed Clean Deploy

Build: 5.8s, both machines updated via rolling strategy, DNS verified.
App live at https://wh-tracker-fly.fly.dev

### 5. AUTH_REQUIRED Flip Command Ready

```bash
fly secrets set AUTH_REQUIRED=true --app wh-tracker-fly
```

**NOT flipped yet** — waiting for real users to be seeded first so no one gets locked out.

---

## Current Production State

- **URL:** https://wh-tracker-fly.fly.dev
- **Alembic head:** `l6m7n8o9p0q1`
- **Auth:** OTP login working; `AUTH_REQUIRED` still false (routes not yet enforced)
- **Users:** id=1 amcgrean@beisserlumber.com (admin), id=2 po-test@beisserlumber.com (non-functional)
- **PO module:** Fully functional, backed by materialized view, 15-min pg_cron refresh
- **Kiosk/TV:** Intentionally unauthenticated — do not gate these

---

## What Needs To Happen Next (in order)

### Priority 1 — Apply @login_required to All Non-Kiosk Routes

This is the main blocking item before flipping auth on.

**Files to update — add `@login_required` to every route handler:**

| File | Notes |
|------|-------|
| `app/Routes/main/picks.py` | Gate all routes |
| `app/Routes/main/work_orders.py` | Gate all routes |
| `app/Routes/main/warehouse.py` | Gate all routes |
| `app/Routes/main/supervisor.py` | Gate all routes |
| `app/Routes/main/delivery.py` | Gate all routes |
| `app/Routes/main/credits.py` | Gate all routes |
| `app/Routes/main/search.py` | Gate all routes |
| `app/Routes/main/api.py` | Gate all routes (JSON endpoints) |
| `app/Routes/sales/transactions.py` | Gate all routes |
| `app/Routes/sales/hub.py` | Gate all routes |
| `app/Routes/sales/history.py` | Gate all routes |
| `app/Routes/sales/api.py` | Gate all routes |
| `app/Routes/sales/customers.py` | Gate all routes |
| `app/Routes/sales/reports.py` | Gate all routes |
| `app/Routes/dispatch/board.py` | Gate all routes |
| `app/Routes/dispatch/stops.py` | Gate all routes |
| `app/Routes/dispatch/api.py` | Gate all routes |
| `app/Routes/files.py` | Gate all routes |

**DO NOT gate:**
- `app/Routes/main/kiosk.py` — warehouse floor kiosk, must stay open
- `app/Routes/main/tv.py` — branch TV wallboard, must stay open
- `app/Routes/main/health.py` — health check endpoint, must stay open
- `app/Routes/auth/` — login routes, must stay open

**Import pattern (already has the decorator, just needs applying):**
```python
from app.auth import login_required

@main_bp.route('/my-route')
@login_required
def my_route():
    ...
```

For admin-only routes, use `@role_required('admin')` which also enforces login:
```python
from app.auth import role_required

@main_bp.route('/admin-thing')
@role_required('admin')
def admin_thing():
    ...
```

### Priority 2 — Seed Real Users

Use the admin UI at `/auth/users` or provide a CSV list for code seeding.

Role assignments:
- Warehouse/picking staff → `warehouse` role, branch = home branch
- Purchasing staff → `purchasing` role, branch = home branch
- Ops reviewers → `ops` role, branch = home branch
- Supervisors → `supervisor` role (all branches)
- Sales reps → `sales` role, user_id = ERP rep ID (e.g. `mschmit`)

`user_id` field = ERP rep ID — must match `salesperson`/`order_writer` in ERP data
for "My Orders" views to work correctly.

### Priority 3 — Flip AUTH_REQUIRED=true

After routes are gated and users seeded:
```bash
fly secrets set AUTH_REQUIRED=true --app wh-tracker-fly
```

Triggers automatic machine restart. Verify login flow works end-to-end.

### Priority 4 — PO End-to-End Browser Test (manual)

1. Log in as `amcgrean@beisserlumber.com`
2. Go to `/po/` — 3-step check-in wizard
3. Look up PO `305500` (Andersen Logistics, 10FD branch)
4. Upload a photo
5. Submit, then review at `/po/review`

### Priority 5 — Kiosk/TV Branch Filtering

WorkOrder routes and TV board can be branch-filtered. Pick routes cannot yet. Full
spec in prior `next-agent-prompt.md`. Deferred — not blocking auth go-live.

### Priority 6 — Phase 2 Auth (future)

SMS OTP + PIN login for warehouse/driver roles. Not started. Entry point: mobile app.

---

## Architecture Rules (permanent, do not regress)

1. **TRIM joins** — `central_db_mode` queries on `cust_key`/`seq_num` must use `TRIM()`.
2. **No system_id on customer joins** — `erp_mirror_cust`/`erp_mirror_cust_shipto` are centralized.
3. **admin bypass** — `@role_required` and `_is_allowed()` short-circuit for `admin`. Keep in sync.
4. **IF NOT EXISTS on migrations** — Use raw SQL guards for columns that may have been applied outside Alembic.
5. **R2 for uploads** — New upload flows use R2 via boto3. Never `UPLOAD_FOLDER` for new features.
6. **No Supabase client** — SQLAlchemy + psycopg2 only.
7. **UPPER(COALESCE()) for string comparisons** — ERP data is mixed case.
8. **expand_branch_filter()** — Never use `== branch` when branch could be `DSM`.
9. **app_po_header is a materialized view** — Do NOT drop/recreate as regular view.
   pg_cron job id=1 refreshes it every 15 min. Manual refresh at `POST /po/api/admin/refresh-cache`.
10. **Kiosk/TV routes are unauthenticated by design** — `/kiosk/<branch>/*` and `/tv/<branch>/*`
    are warehouse floor screens. Never add `@login_required` to `kiosk.py` or `tv.py`.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `app/auth.py` | `login_required`, `role_required`, session keys — source of truth |
| `app/navigation.py` | Role-gated nav — already complete, no changes needed |
| `app/Routes/auth/admin.py` | User CRUD at `/auth/users` |
| `app/Routes/auth/login.py` | OTP login/verify/logout |
| `app/Routes/main/kiosk.py` | **EXEMPT from auth** — warehouse kiosk |
| `app/Routes/main/tv.py` | **EXEMPT from auth** — branch TV board |
| `app/Routes/po_routes.py` | PO blueprint — all routes including refresh endpoint |
| `app/Services/po_service.py` | PO query functions |

## Fly.io Quick Commands

```bash
fly deploy
fly logs --app wh-tracker-fly --no-tail
fly ssh console --app wh-tracker-fly -C "flask db current"
fly secrets set AUTH_REQUIRED=true --app wh-tracker-fly
fly secrets list --app wh-tracker-fly
```

# Agent Handoff — WH-Tracker → beisser-takeoff Migration
**Date:** 2026-04-01  
**Next task:** Migrate WH-Tracker modules into beisser-takeoff (Next.js), starting with Auth

---

## What you have access to

You are running locally with access to **two repos**:
- `WH-Tracker` — Flask/Python app, Fly.io, the ops platform being migrated FROM
- `beisser-takeoff` — Next.js app, currently on Vercel (moving to Fly.io), migrating INTO

Both share the **same Supabase Postgres instance**:
- `public` schema — WH-Tracker tables (Alembic managed)
- `bids` schema — beisser-takeoff tables (Drizzle managed)

---

## Architecture context

### Current state
```
wh-tracker-fly.fly.dev  →  WH-Tracker (Flask, Python 3.11)
                            - Pick/pack, warehouse, dispatch, sales, purchasing
                            - ERP sync worker (sync_erp.py) polls Pi every 5s
                            - Jinja2 templates, Bootstrap 4 UI

beisser-takeoff.vercel.app  →  beisser-takeoff (Next.js)
                                - Lumber estimating / takeoff / bid management
                                - bids schema: 8,999 bids, 4,941 customers, 102,997 jobs
```

### Target state (end state)
```
beisser.cloud  →  beisser-takeoff (Next.js, Fly.io)  ← unified app
                  sync_erp.py (Fly.io)                ← background worker only
```

WH-Tracker Flask modules get rebuilt as Next.js pages in beisser-takeoff one
by one (strangler fig). Flask stays alive as API backend until each module is
migrated, then retires.

---

## Database

**Supabase project ID:** `vyatosniqboeqzadyqmr` (us-east-1 / iad)

### public schema (WH-Tracker, Alembic)
Key tables:
- `app_users` — authenticated users. Columns: id, email, user_id (ERP rep ID),
  display_name, roles (JSON array), branch, is_active, estimating_user_id
- `otp_codes` — one-time login codes for passwordless auth
- `erp_mirror_*` — ERP data synced from Agility ERP via Pi sync worker
  - `erp_mirror_so_header` — 1M+ sales order headers
  - `erp_mirror_so_detail` — 4.5M SO line items
  - `erp_mirror_cust` — 4,925 customers
  - `erp_mirror_cust_shipto` — 145K ship-to addresses
  - `erp_mirror_wo_header` — 253K work orders
  - (+ many more, see docs/migration-state.md)
- `pick`, `pickster`, `PickTypes` — warehouse pick tracking
- `dispatch_*` — delivery route/stop/driver tables
- `purchasing_*` — buyer workflow tables
- `files`, `file_versions` — polymorphic R2 file attachments
- Current Alembic head: `t3u4v5w6x7y8`

### bids schema (beisser-takeoff, Drizzle)
- `bids.bid` — 8,999 bids
- `bids.customer` — 4,941 customers (legacy, from Neon migration)
- `bids.job` — 102,997 jobs
- `bids.user` — 69 users (password column = 'OTP_AUTH_ONLY', auth moves to WH-Tracker OTP)
- `bids.estimator` — 7 estimators
- `bids.designer` — 4 designers
- `bids.design` — 851 designs
- `bids.takeoff_sessions`, `bids.takeoff_groups` — active takeoff data
- All new UUID-based tables: bids, bid_versions, products, assemblies, etc.

### app_users — current linked accounts
| email | roles | estimating_user_id |
|-------|-------|-------------------|
| amcgrean@beisserlumber.com | [admin, estimator] | 2 |
| rboes@beisserlumber.com | [estimator] | 3 |
| kpeters@beisserlumber.com | [estimator] | 4 |
| alarsen@beisserlumber.com | [designer] | 5 |
| dstevens@beisserlumber.com | [estimator] | 34 |
| jrohlf@beisserlumber.com | [estimator] | 42 |
| jcking@beisserlumber.com | [estimator] | 43 |
| mhackett@beisserlumber.com | [estimator, designer] | 63 |
| mblevins@beisserlumber.com | [designer] | 66 |
| mwagenknecht@beisserlumber.com | [designer] | 68 (inactive) |

---

## WH-Tracker Auth system (what beisser-takeoff needs to adopt)

### How it works
1. User enters email at `/auth/login`
2. Flask generates a 6-digit OTP, stores in `otp_codes` table, sends via email
3. User enters OTP at `/auth/verify`
4. On success: session is set with `user_id`, `user_email`, `user_roles`,
   `user_rep_id` (ERP ID), `user_display_name`, `user_branch`
5. Sessions are permanent (7-day lifetime), stored server-side

### Key files in WH-Tracker
- `app/Routes/auth/` — login, verify, resend, logout routes
- `app/auth.py` — `is_authenticated()`, `get_current_user()`, `login_required`,
  `role_required(*roles)` decorators
- `app/Models/models.py` — `AppUser`, `OTPCode` models

### Session keys
```python
SESSION_USER_ID = "user_id"           # AppUser.id
SESSION_USER_EMAIL = "user_email"
SESSION_USER_REP_ID = "user_rep_id"   # ERP rep ID e.g. "mschmit"
SESSION_USER_NAME = "user_display_name"
SESSION_USER_ROLES = "user_roles"     # list[str]
SESSION_USER_BRANCH = "user_branch"   # e.g. "20GR"
```

### Role system
Roles stored as JSON array in `app_users.roles`. No enum — free text strings.
Current values: admin, ops, sales, picker, supervisor, warehouse, production,
purchasing, manager, delivery, dispatch, credits, estimator, designer.
`admin` bypasses all role checks.

---

## ERP data layer (critical context for migrating modules)

The ERP mirror tables in Supabase contain all the data. The Python
`erp_service.py` (~145KB) has all query logic. When migrating each module to
Next.js, the queries need to be rewritten in TypeScript hitting Supabase
directly.

### Critical SQL rules (data integrity)
1. **Always use `UPPER(COALESCE(col, ''))` for string comparisons** — ERP stores
   mixed case (`sale_type` = `WillCall`, `Direct`, `XInstall`). Use uppercase
   literals. Silent wrong results if you forget this.
   ```sql
   -- CORRECT
   WHERE UPPER(COALESCE(sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL')
   -- WRONG — silently returns wrong data
   WHERE sale_type NOT IN ('Direct', 'WillCall', 'XInstall')
   ```

2. **Count distinct SOs, never lines** — `erp_mirror_so_detail` has 4.5M rows.
   Always `COUNT(DISTINCT so_id)` for order counts, never `COUNT(*)` on detail.

3. **Branch identifiers**: 20GR (Grimes), 25BW (Birchwood), 40CV (Coralville),
   10FD (Fort Dodge), DSM = 20GR+25BW combined view.

4. **SO number normalization** — barcodes have leading zeros (`0001463004`) but
   ERP stores `1463004`. Strip leading zeros before querying.

### Key ERP fields
- `so_status`: O=Open, I=Invoiced, C=Closed, H=Hold
- `sale_type`: WillCall, Direct, XInstall, Hold, CM (credit memo) — anything
  else = delivery/add-on order
- `salesperson` = account rep (agent_1), `order_writer` = order writer (agent_3)
- `system_id` = branch code (20GR, 25BW, etc.)
- `expect_date` = expected delivery date (primary filter date)

---

## Cloudflare R2 file storage

Both apps use the same R2 bucket. WH-Tracker's `File` model uses polymorphic
`entity_type` + `entity_id`. beisser-takeoff can attach files using
`entity_type='bid'` or `entity_type='design'` with no schema changes.

File upload endpoint (currently on WH-Tracker Flask):
```
POST /files/upload   multipart/form-data
  file, entity_type, entity_id, category (opt), change_note (opt)
→ { id, key, ... }

GET  /files/<id>          → presigned R2 URL redirect
GET  /files/entity/bid/<id>  → list all files for a bid
```

---

## Cross-app API (WH-Tracker exposes to beisser-takeoff)

```
GET /api/customers/search?q=<term>&branch=<branch>&limit=<n>
Header: X-Api-Key: <INTERNAL_API_KEY>
→ { customers: [{ code, name, city, state, branch }] }
```

`INTERNAL_API_KEY` is set as Fly secret on WH-Tracker and Vercel env var on
beisser-takeoff.

```
GET /api/health
→ { status: "ok"|"degraded", version: "<sha>", db: "ok"|"error" }
```

---

## Migration task — START HERE: Auth

beisser-takeoff currently has its own login backed by `bids.user` (legacy
Neon passwords now set to `'OTP_AUTH_ONLY'`). The goal is to replace it with
WH-Tracker's OTP flow so users have one login for the whole unified app.

### What "auth migration" means
1. **In beisser-takeoff (Next.js):** Replace current login UI/logic with a flow
   that calls WH-Tracker's auth OR implement the same OTP pattern natively
   in Next.js against the `app_users` / `otp_codes` tables in Supabase.

2. **Recommended approach — native Next.js OTP:**
   - Build `/login` page in Next.js (email input → OTP input)
   - API route `POST /api/auth/request-otp` — insert into `otp_codes` table,
     send email via same email provider WH-Tracker uses
   - API route `POST /api/auth/verify-otp` — verify code, create session
   - Use `iron-session` or similar for server-side sessions
   - Role/permission checks read from `app_users.roles`
   - Look at `app/Routes/auth/` in WH-Tracker for exact OTP logic to port

3. **Do NOT use Supabase Auth** — auth is intentionally custom (OTP via email
   using `otp_codes` table), not Supabase's built-in auth. This keeps one
   unified user record in `app_users` for both apps.

### After auth is done
Each subsequent module migration follows the same pattern:
1. Build the page in Next.js using Supabase queries
2. Apply the same role gates (`app_users.roles`)
3. Retire the Flask route (or leave as redirect stub)

---

## Environment variables

### WH-Tracker (Fly secrets)
```
DATABASE_URL          = Supabase connection string
SECRET_KEY            = Flask session secret
AUTH_REQUIRED         = true
ESTIMATING_APP_URL    = https://beisser.cloud
INTERNAL_API_KEY      = UH1Q6ccd7VP3g4rbKO0B9fU0pGyyJhdj  ← rotate this
R2_ACCESS_KEY_ID      = ...
R2_SECRET_ACCESS_KEY  = ...
R2_ENDPOINT_URL       = https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET             = liveedgefiles
```

### beisser-takeoff (Vercel env vars)
```
BIDS_DATABASE_URL     = Supabase direct connection (port 5432)
INTERNAL_API_KEY      = UH1Q6ccd7VP3g4rbKO0B9fU0pGyyJhdj  ← same key, rotate
```

---

## Deployment notes

- WH-Tracker auto-runs Alembic migrations on Fly startup
  (`RUN_MIGRATIONS_ON_START=true`)
- beisser-takeoff uses Drizzle for `bids` schema migrations — run manually
- When deploying beisser-takeoff to Fly (future), use `output: 'standalone'`
  in `next.config.js` and deploy to `iad` region (same as Supabase us-east-1)
- Both apps on Fly.io in `iad` = ~1ms DB round trips

---

## What NOT to do

- Do not alter existing WH-Tracker Flask routes while migrating — run them in
  parallel until the Next.js replacement is confirmed working
- Do not use Supabase Auth — use the custom `app_users` / `otp_codes` pattern
- Do not add tables to `public` schema from beisser-takeoff — use `bids` schema
- Do not add tables to `bids` schema from WH-Tracker — use `public` schema
- Do not break the ERP sync worker (`sync_erp.py`) — it's the data pipeline

# Next Agent Handoff — 2026-03-30

## Session Summary

This session completed the **PO Check-In Module** migration from the standalone `po-app` (Next.js/Supabase) into WH-Tracker as a Flask blueprint, and resolved all blocking issues preventing first login on the new Fly.io deployment.

---

## What Was Done This Session

### 1. PO Blueprint — Fully Wired

**New files:**
- `app/Routes/po_routes.py` — Full blueprint (`po`, prefix `/po`) with all worker, review, open-PO, and JSON API routes
- `app/Services/po_service.py` — Python equivalents of the Supabase RPC functions: `search_purchase_orders`, `list_open_pos_for_branch`, `get_purchase_order`, `get_submission_summary_for_pos`
- `app/templates/po/checkin.html` — 3-step check-in wizard
- `app/templates/po/history.html` — Worker submission history
- `app/templates/po/review_dashboard.html` — Ops/supervisor/admin submission list with 15s polling
- `app/templates/po/review_detail.html` — Single submission detail + review form
- `app/templates/po/open_pos.html` — Open PO list (supervisor/admin)
- `app/templates/po/open_po_detail.html` — Full PO detail with lines, receiving summary, photo gallery

**Modified files:**
- `app/Models/models.py` — Added `POSubmission` model and `branch` field to `AppUser`
- `app/__init__.py` — Registered `po_blueprint`
- `app/auth.py` — Added `SESSION_USER_BRANCH` constant
- `app/navigation.py` — Replaced coming-soon Purchasing section with real nav items; **fixed `_is_allowed()` to short-circuit for `admin` role** (was only checking `*` wildcard — admin users couldn't see nav sections that didn't explicitly list `admin`)
- `app/Routes/auth_routes.py` — Added `branch` field to add/edit user forms
- `app/templates/auth/add_edit_user.html` — Branch dropdown (20GR, 25BW, 10FD, 40CV)
- `app/templates/auth/manage_users.html` — Branch column in user list
- `config.py` — Added R2 config (R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL)
- `requirements.txt` — Added `boto3`

### 2. Alembic Migrations Applied to Production

Three new migrations, all applied to production DB:

| Revision | Description |
|---|---|
| `i3j4k5l6m7n8` | Create `app_users` + `otp_codes` tables (was pending) |
| `j4k5l6m7n8o9` | Add `branch_code` to pick tables — **fixed** to use `IF NOT EXISTS` (columns existed from direct SQL, migration hadn't recorded them) |
| `k5l6m7n8o9p0` | Add `branch VARCHAR(16)` to `app_users` — using `IF NOT EXISTS` for safety |
| `l6m7n8o9p0q1` | Create `po_submissions` table with all indexes |

**Alembic head is now:** `l6m7n8o9p0q1`

### 3. First Admin User Created

- `amcgrean@beisserlumber.com` — id: 1, role: `admin`, active
- Created via Python on the Fly machine (tables were brand new, no users existed)

### 4. Auth Confirmed Working

- OTP email login works end-to-end via Resend
- Fly secrets `RESEND_API_KEY` and `OTP_EMAIL_FROM` were already set
- R2 secrets all set: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`, `R2_PUBLIC_URL`

---

## Current Production State

- **URL:** https://wh-tracker-fly.fly.dev
- **Alembic head:** `l6m7n8o9p0q1`
- **Users in DB:** 1 (amcgrean@beisserlumber.com, admin)
- **PO module:** Routes and templates deployed; `app_po_*` views in DB not yet verified
- **Auth:** Email OTP only (Phase 1)

---

## What Needs To Happen Next

### Priority 1 — PO Module: Verify DB Views

The PO module requires these read-model views to exist in the Supabase DB:
- `app_po_search`
- `app_po_header`
- `app_po_detail`
- `app_po_receiving_summary`

Check if they exist:
```bash
fly ssh console --app wh-tracker-fly -C "python -c \"
import sys; sys.path.insert(0, '/app')
from app import create_app
from app.extensions import db
from sqlalchemy import text
app = create_app()
with app.app_context():
    for v in ['app_po_search','app_po_header','app_po_detail','app_po_receiving_summary']:
        try:
            db.session.execute(text(f'SELECT 1 FROM {v} LIMIT 1'))
            print(f'EXISTS: {v}')
        except Exception as e:
            print(f'MISSING: {v} — {e}')
\""
```

If missing, apply `sql/app_po_read_models.sql` from the `po-app` repo. These are read-only views over ERP mirror tables — no writes needed.

### Priority 2 — Add More Users

Admin must create all users via `/auth/users` before they can log in. All users start with no account — email OTP will silently do nothing if the address isn't registered.

Key users to add:
- Other admins/supervisors
- Ops users (with `branch` set to their home branch)
- Warehouse/purchasing users (for PO check-in testing)

### Priority 3 — End-to-End PO Check-In Test

1. Log in as a `purchasing` or `warehouse` role user
2. Go to `/po/`
3. Try the 3-step wizard: scan/enter a PO → take a photo → submit
4. Review the submission at `/po/review` as an `ops`/`supervisor` user

### Priority 4 — Kiosk/TV Branch Filtering (deferred from previous sessions)

See `docs/next-agent-prompt.md` for the full spec. Still pending:
- WorkOrder routes can be branch-filtered (`branch_code` column exists)
- TV board can be filtered via `expand_branch_filter()`
- Pick-related routes cannot be filtered (no `branch_code` on Pickster/Pick/PickAssignment yet)

### Priority 5 — Phase 2 Auth (mobile app, planned)

**Not started. Do not build until the mobile app project begins.**
- SMS/phone OTP for warehouse workers and drivers (Twilio or Resend SMS)
- PIN login for shared kiosk/tablet devices
- Both scoped to `warehouse`/`purchasing`/`delivery` roles only
- Entry point: mobile app (not the web app)
- Hook already in `otp_service.py` — `send_otp_sms()` is stubbed with a Phase 2 note

---

## Architecture Rules (permanent, do not regress)

1. **TRIM joins** — All `central_db_mode` mirror queries joining on `cust_key` or `seq_num` must use `TRIM()`. See `memory/project_cust_key_trim_fix.md`.
2. **No system_id on customer joins** — `erp_mirror_cust` / `erp_mirror_cust_shipto` are centralized (`00CO`). Never join them on `system_id`.
3. **admin bypass** — `@role_required` and `_is_allowed()` in navigation both short-circuit for `admin`. Keep them in sync.
4. **IF NOT EXISTS migrations** — Any migration touching columns/tables that may have been applied outside Alembic should use raw SQL with `IF NOT EXISTS` guards.
5. **R2 for file storage** — All user-uploaded files go to R2 via boto3. Never use `UPLOAD_FOLDER` for new upload flows.
6. **No Supabase client** — WH-Tracker uses SQLAlchemy + psycopg2 directly against the Supabase Postgres URL. No `supabase-py` or Supabase JS client.

---

## Key Files

| File | Purpose |
|------|---------|
| `app/Routes/po_routes.py` | PO blueprint — all routes |
| `app/Services/po_service.py` | PO query functions (wraps ERP mirror + po_submissions) |
| `app/templates/po/` | All 6 PO templates |
| `app/Services/otp_service.py` | OTP generation, email delivery, Phase 2 SMS stub |
| `app/Routes/auth_routes.py` | Login, OTP verify, user management |
| `app/Models/models.py` | AppUser (with branch), POSubmission, OTPCode |
| `app/navigation.py` | Nav sections + `_is_allowed()` with admin bypass |
| `app/branch_utils.py` | Branch normalization, DSM expansion |
| `app/Services/erp_service.py` | All ERP queries (central_db_mode + legacy) |
| `migrations/versions/` | Alembic migrations — head is `l6m7n8o9p0q1` |

---

## Fly.io Quick Commands

```bash
# Deploy
fly deploy

# Check logs
fly logs --app wh-tracker-fly --no-tail

# Migration state
fly ssh console --app wh-tracker-fly -C "flask db current"

# Run migrations manually
fly ssh console --app wh-tracker-fly -C "flask db upgrade"

# List secrets
fly secrets list --app wh-tracker-fly
```

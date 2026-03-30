# Agent Handoff — Passwordless Auth System
**Date:** 2026-03-30
**Branch:** `main-fly` (NOT merged to `main`)
**Repo:** amcgrean/WH-Tracker

---

## What This Branch Does vs `main`

`main-fly` is ahead of `main` by roughly 30 commits. The entire Fly.io deployment
infrastructure, the dispatch console overhaul, AND the auth system described below
are all on `main-fly` only. `main` does not have any of this.

Key commits on `main-fly` not in `main` (most recent first, relevant to auth):

| Commit | Description |
|--------|-------------|
| `ba12347` | Add Resend as primary OTP email provider |
| `7a8e781` | Add passwordless email OTP authentication system |
| `4c91d7a` | Reorganize sidebar nav (Dispatch/Sales/Inventory/Purchasing/Admin) |
| `57cdec8` | Fix type mismatch on erp_mirror so_id joins |
| (many more) | Fly.io deployment scaffolding, dispatch console, migration work |

---

## Auth System — What Is Already Built

### Database Schema (`migrations/versions/i3j4k5l6m7n8_add_auth_tables.py`)
Two new tables:

**`app_users`** — one row per person who can log in
- `id`, `email` (unique, lowercase), `user_id` (ERP rep ID e.g. `mschmit`),
  `display_name`, `phone` (Phase 2 placeholder), `roles` (JSON array),
  `is_active`, `created_at`, `last_login_at`

**`otp_codes`** — ephemeral codes sent during login
- `id`, `email`, `code` (6-digit), `created_at`, `expires_at`, `used`

**Migration status:** Migration file exists and is in the Alembic chain. If the
migration has NOT been run on the Supabase DB yet, run:
```bash
fly ssh console --app wh-tracker-fly -C "sh -c 'cd /app && flask db upgrade'"
```
Or apply directly in Supabase SQL editor — see the migration file for exact DDL.

---

### Core Files

| File | Purpose |
|------|---------|
| `app/auth.py` | Session constants, `get_current_user()`, `login_required`, `role_required` decorators |
| `app/Routes/auth_routes.py` | Blueprint `/auth` — login, verify, logout, admin user CRUD |
| `app/Services/otp_service.py` | OTP generation, rate-limiting, verification, email delivery |
| `app/Models/models.py` | `AppUser` + `OTPCode` SQLAlchemy models |
| `app/templates/auth/login.html` | Email entry form |
| `app/templates/auth/verify.html` | 6-digit code entry form |
| `app/templates/auth/manage_users.html` | Admin — list/toggle/delete users |
| `app/templates/auth/add_edit_user.html` | Admin — add or edit a user |
| `scripts/seed_users.py` | Seed initial users — edit SEED_USERS list and run |

---

### Login Flow

```
GET /auth/login  →  user enters email
POST /auth/login →  OTP generated, emailed via Resend, redirect to /auth/verify
POST /auth/verify → code checked → session set → redirect to / or ?next=
POST /auth/logout → session cleared → redirect to /auth/login
```

Session keys stored on successful login:
- `user_id` — AppUser.id (int, FK)
- `user_email` — e.g. `mschmit@beisserlumber.com`
- `user_rep_id` — ERP rep/employee ID e.g. `mschmit` (used to filter sales views)
- `user_display_name` — e.g. `Mike Schmidt`
- `user_roles` — list of strings e.g. `["sales"]`

Sessions persist 7 days (`PERMANENT_SESSION_LIFETIME = timedelta(days=7)` in config).

---

### Email Delivery (Resend)

`otp_service.py` auto-selects delivery method:
1. `AUTH_OTP_CONSOLE=true` → prints code to console (dev only, skip email)
2. `RESEND_API_KEY` set → uses Resend HTTP API (**this is what production uses**)
3. Fallback → SMTP (Office 365 or any STARTTLS)

**Resend domain `beisser.cloud` is already verified in Resend** (verified March 4, 2026).

Required Fly secrets for Resend:
```bash
fly secrets set RESEND_API_KEY=re_xxxxxxxxxx
fly secrets set OTP_EMAIL_FROM=noreply@beisser.cloud
```

---

### Enabling Authentication (AUTH_REQUIRED flag)

Auth is **off by default** via `AUTH_REQUIRED` env var. The app runs normally
without login until you flip this on:

```bash
fly secrets set AUTH_REQUIRED=true
```

When `AUTH_REQUIRED=false` (or unset), all routes are accessible — good for
testing the rest of the app before enabling auth for users.

---

### Admin User Management (`/auth/users`)

Admin users can:
- View all users (active/inactive)
- Add users manually
- Edit email, display name, ERP rep ID (`user_id`), roles, phone
- Toggle active/inactive
- Delete users
- **Import from Pickers** — a panel on the manage page reads all `Pickster` records
  and lets admin create login accounts from existing pickers in one click

Nav link: Admin sidebar → "Login Accounts" (visible to `admin` role only)

---

### Role System

Defined roles (in `auth_routes.py` `AVAILABLE_ROLES`):
- `admin` — full access, bypasses all role checks
- `ops`
- `warehouse`
- `supervisor`
- `production`
- `delivery`
- `dispatch`
- `sales`

Usage in route files:
```python
from app.auth import login_required, role_required

@bp.route('/something')
@login_required
def something(): ...

@bp.route('/admin-only')
@role_required('admin')
def admin_only(): ...

@bp.route('/ops-or-admin')
@role_required('ops', 'admin')
def ops_view(): ...
```

Navigation visibility by role is controlled in `app/navigation.py`.

---

### ERP User ID / Rep ID Linking

`AppUser.user_id` stores the ERP rep identifier (e.g. `mschmit`). On login this
is written to `session["user_rep_id"]`. Any route that needs to filter by the
logged-in rep can do:

```python
from app.auth import get_current_user
user = get_current_user()
rep_id = user["user_id"]  # e.g. "mschmit"
# use rep_id to filter open orders, open POs, etc.
```

This is the bridge between `mschmit@BEISSERLUMBER.COM` (email login) and
`mschmit` (ERP filter key).

---

### Seeding Initial Users

Edit `scripts/seed_users.py` — update the `SEED_USERS` list with real names/emails/roles, then:

```bash
# locally (with DATABASE_URL set)
python scripts/seed_users.py

# on Fly
fly ssh console --app wh-tracker-fly -C "python /app/scripts/seed_users.py"
```

The script is idempotent — existing users (matched by email) are updated, not duplicated.

---

## What Is NOT Done Yet / Phase 2

### Navigation/menu gating by role
- `navigation.py` has the sidebar structure but individual nav items are not yet
  conditionally shown/hidden based on `user_roles`.
- **Next step:** In `navigation.py`, add a `roles` key to each nav item definition
  and filter in the template or the nav builder. The session roles are available
  in `session["user_roles"]` or via `get_current_user()["roles"]`.

### Route-level auth enforcement
- Most existing routes do NOT yet have `@login_required` or `@role_required` applied.
- **Next step:** Decide which routes are public vs. protected and apply decorators.
  Suggested approach: protect everything with `@login_required` at the blueprint
  level and selectively `@role_required` for admin/sales-specific views.

### Phase 2 — Phone / SMS OTP
- `AppUser.phone` column already exists (migration already has it).
- `otp_service.py` has a comment: `# Phase 2 note: add send_otp_sms(phone, code) here using Twilio`
- `.env.example` has Twilio stubs (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`)
- `auth_routes.py` has a comment: `# Phase 2: add /auth/login-phone and /auth/verify-phone`
- **Nothing needs to be built yet** — the schema and stubs are ready.

### OTP code cleanup job
- Old/expired `otp_codes` rows accumulate in the DB.
- **Next step (low priority):** Add a periodic cleanup query or a Fly cron to
  `DELETE FROM otp_codes WHERE expires_at < now() - interval '24 hours'`.

---

## Activation Checklist (in order)

1. [ ] Run migration to create `app_users` + `otp_codes` tables in Supabase
2. [ ] Set Fly secrets: `RESEND_API_KEY` and `OTP_EMAIL_FROM=noreply@beisser.cloud`
3. [ ] Seed initial users: edit `scripts/seed_users.py` and run it
4. [ ] Test login flow end-to-end with `AUTH_REQUIRED=false` (check `/auth/login` directly)
5. [ ] Apply `@login_required` to routes that should be protected
6. [ ] Set `AUTH_REQUIRED=true` on Fly to enforce auth site-wide
7. [ ] Gate nav items by role in `navigation.py`

---

## Key Environment Variables

```bash
# --- Auth control ---
AUTH_REQUIRED=false          # flip to true to enforce login

# --- Resend (preferred for prod) ---
RESEND_API_KEY=re_xxxx        # your Resend API key
OTP_EMAIL_FROM=noreply@beisser.cloud  # beisser.cloud is verified in Resend

# --- Dev shortcut (prints OTP to console, no email sent) ---
AUTH_OTP_CONSOLE=true

# --- SMTP fallback (not needed if RESEND_API_KEY is set) ---
OTP_SMTP_SERVER=smtp.office365.com
OTP_SMTP_PORT=587
OTP_EMAIL_FROM=you@beisserlumber.com
OTP_SMTP_USER=you@beisserlumber.com  # use "resend" for Resend SMTP relay
OTP_EMAIL_PASSWORD=yourpassword

# --- Phase 2 Twilio stubs (not built yet) ---
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

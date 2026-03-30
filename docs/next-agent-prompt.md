# Next Agent Prompt — WH-Tracker (current as of 2026-03-30)

## What You're Working On

Flask warehouse management app for Beisser Lumber (`wh-tracker-fly` on Fly.io). The app is live at https://wh-tracker-fly.fly.dev.

**Read memory files first** — they live at `.claude/projects/C--Users-amcgrean-python-wh-tracker-fly-WH-Tracker/memory/`. Start with `MEMORY.md` for the index.

Also read `docs/NEXT_AGENT_HANDOFF_2026-03-30.md` for the full session record of what was just built.

---

## Current State (as of 2026-03-30)

### What's Complete
- **UI/UX overhaul Phases 0-7** — done (see `project_ui_overhaul_status.md`)
- **PO Check-In blueprint** — routes, service layer, templates, migrations all deployed
- **Auth** — OTP email login live via Resend; admin user created; `admin` role bypasses all nav/route checks
- **Alembic head** — `l6m7n8o9p0q1` (`po_submissions` table created)
- **R2 storage** — Fly secrets set; `po_service.py` wires R2 via boto3

### What's Not Done Yet (priority order)

1. **Verify `app_po_*` DB views exist** — PO module won't work without them. Check then apply `sql/app_po_read_models.sql` from po-app repo if missing. Views: `app_po_search`, `app_po_header`, `app_po_detail`, `app_po_receiving_summary`.

2. **Create users** — DB has only 1 user (amcgrean@beisserlumber.com, admin). All users must be added via `/auth/users` before they can log in.

3. **End-to-end PO check-in test** — Needs a purchasing/warehouse user + a real PO number from ERP.

4. **Kiosk/TV branch filtering** — Routes exist but show all branches with a notice. WorkOrder and TV board can be filtered; pick routes cannot yet. See `docs/next-agent-prompt.md` (previous version) for full spec — Task 2 in the kiosk/TV section.

5. **UPLOAD_FOLDER durability** — Local disk, not durable on Fly. Low priority until credit/RMA upload feature is actively used.

6. **Phase 2 auth (mobile app, future)** — SMS OTP + PIN login for warehouse/driver roles. Do not start until mobile app project begins.

---

## Architecture Rules (do not regress)

1. **TRIM joins** — `central_db_mode` queries joining on `cust_key` or `seq_num` must use `TRIM()`. See `memory/project_cust_key_trim_fix.md`.
2. **No system_id on customer joins** — `erp_mirror_cust` / `erp_mirror_cust_shipto` are centralized. Never join them on `system_id`.
3. **admin bypass is consistent** — `auth.py` `_user_has_role()` and `navigation.py` `_is_allowed()` both short-circuit for `admin`. Keep them in sync.
4. **IF NOT EXISTS on migrations** — Any migration adding columns that may have been applied outside Alembic must use raw SQL with `IF NOT EXISTS`.
5. **R2 for uploads** — New file upload flows use R2 via boto3. Never `UPLOAD_FOLDER` for new features.
6. **No Supabase client** — SQLAlchemy + psycopg2 only. No `supabase-py`.
7. **TRIM fix** — Do not remove TRIM from any existing ERP mirror joins.
8. **Read before Edit** — Always read files before editing. Batch-read related files in parallel.
9. **expand_branch_filter()** — Never use `== branch` when branch could be `DSM`. DSM expands to `['20GR', '25BW']`.

---

## Key Files

| File | Purpose |
|------|---------|
| `app/Routes/po_routes.py` | PO blueprint — all routes |
| `app/Services/po_service.py` | PO query functions |
| `app/templates/po/` | 6 PO templates |
| `app/Services/otp_service.py` | OTP email delivery; Phase 2 SMS stub |
| `app/Routes/auth_routes.py` | Login/OTP/user management |
| `app/Models/models.py` | AppUser (+ branch), POSubmission, OTPCode |
| `app/navigation.py` | Nav sections + admin bypass in `_is_allowed()` |
| `app/branch_utils.py` | Branch normalization, DSM expansion |
| `app/Services/erp_service.py` | All ERP queries |
| `app/static/css/style.css` | Global design system |
| `config.py` | All env config including R2 vars |

---

## Pitfalls

1. **Edit tool requires Read first** — always Read before editing. Parallel-read batches.
2. **fly.toml has unstaged local changes** — don't accidentally commit it.
3. **Migration conflicts** — If you hit `DuplicateColumn` or similar, use `IF NOT EXISTS` guards in raw SQL rather than the Alembic helpers.
4. **Session not refreshed after deploy** — Users must log in again after a deploy to pick up session changes.
5. **WorkOrder model** — verify `branch_code` column name before writing queries.
6. **Schema drift** — `so_id` and `seq_num` have integer vs varchar drift between mirror tables. Always CAST in joins.

---

## Fly.io Commands

```bash
fly deploy
fly logs --app wh-tracker-fly --no-tail
fly ssh console --app wh-tracker-fly -C "flask db current"
fly ssh console --app wh-tracker-fly -C "flask db upgrade"
fly secrets list --app wh-tracker-fly
```

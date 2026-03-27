# Next Agent Prompt: Kiosk/TV Branch Filtering, PWA Icons & Cleanup

## Context
You are working on a Flask warehouse management app for Beisser Lumber. The full 8-phase UI/UX overhaul (Phases 0-7) is **COMPLETE** on `main-fly`. A critical customer-name/address bug was also fixed (all central_db_mode queries now use TRIM on cust_key/seq_num joins).

**Read the memory files first** at the path shown in `MEMORY.md`. Key files:
- `project_ui_overhaul_status.md` — All phases done, deferred items listed
- `project_branch_architecture.md` — Dual branch concept (sidebar filter vs kiosk URL)
- `project_design_system.md` — CSS custom properties + reusable classes
- `project_fly_deployment.md` — Fly.io app status

Also read `docs/NEXT_AGENT_HANDOFF_2026-03-27.md` for the full session record.

## What's Done (DO NOT redo)
- **Phases 0-7 UI/UX overhaul** — all complete
- **Customer name/address TRIM fix** (commit `9c86671`) — All 12 central_db_mode mirror queries in `erp_service.py` now use `TRIM(c.cust_key) = TRIM(soh.cust_key)` and `TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))`. This fixed blank customer names across delivery tracker, picks, order board, staged orders, sales orders, invoices, dashboard, and work orders.
- `app/branch_utils.py` — Centralized branch logic (normalize, expand, validate, DSM->[20GR,25BW])
- `app/static/css/style.css` — Full design system (~355 lines)
- `app/templates/base.html` — Sidebar with branch selector, search, PWA manifest/SW registration
- `app/templates/kiosk_base.html` / `tv_base.html` — Standalone shells (no sidebar)
- All kiosk routes (`/kiosk/<branch>/...`) and TV routes (`/tv/<branch>/...`) exist in `app/Routes/routes.py`
- All kiosk templates (7) in `app/templates/kiosk/` and TV templates (2) in `app/templates/tv/`
- Helper functions `_kiosk_context(branch)` and `_tv_context(branch)` validate branch and build template context

---

## Task 1: PWA Icons (quick)

Create two PNG icons and place in `app/static/icons/`:
- `icon-192.png` (192x192)
- `icon-512.png` (512x512)

Design: Simple "B" or cubes/warehouse icon on solid green `#004526` background, white foreground. These are referenced by `app/static/manifest.json`. You can generate these programmatically with Python (Pillow) if you prefer — just make them clean and legible.

---

## Task 2: Kiosk/TV Branch-Aware Data Filtering (main task)

### Current State
All 13 kiosk/TV route functions in `app/Routes/routes.py` call `_kiosk_context(branch)` or `_tv_context(branch)` which **validates** the branch from the URL path — but then **ignores it for data queries**. Templates show a notice badge saying "Showing all branches."

### What Needs To Happen

**WorkOrder routes CAN be filtered** (WorkOrder model has `branch_code`):
- `kiosk_work_orders(branch)` — Filter `WorkOrder.query` by `branch_code`
- `kiosk_work_orders_open(branch, user_id)` — Filter open WOs by branch
- `kiosk_work_order_scan(branch, user_id)` — Filter scannable WOs by branch
- `kiosk_work_order_select(branch)` — Filter selectable WOs by branch
- `kiosk_start_work_orders(branch)` — Validate selected WOs belong to branch
- `kiosk_complete_work_order(branch, wo_id)` — Validate WO belongs to branch

**ERP mirror data CAN be filtered** (ERP tables have `branch_code`):
- `tv_board_branch(branch, handling_code)` — The `erp_service` queries can filter by branch using `expand_branch_filter()` from `branch_utils` (this pattern is already used in sales/dispatch routes)

**Pick data CANNOT be filtered** (Pickster, Pick, PickAssignment have NO `branch_code`):
- `kiosk_pickers(branch)` — Shows all pickers. Keep the "Showing all pickers" notice.
- `kiosk_confirm_picker(branch, picker_id)` — No filtering possible.
- `kiosk_input_pick(branch, picker_id, pick_type_id)` — No filtering possible.
- `kiosk_complete_pick(branch, pick_id)` — No filtering possible.
- `tv_open_picks(branch)` — Shows all open picks. Keep the notice.

### Implementation Pattern
Follow the pattern already used in `app/Routes/sales_routes.py`:
```python
from app.branch_utils import normalize_branch, expand_branch_filter

# For WorkOrder queries:
branch = ctx['kiosk_branch']  # Already normalized by _kiosk_context
if branch:
    branch_list = expand_branch_filter(branch)  # DSM -> ['20GR', '25BW']
    query = query.filter(WorkOrder.branch_code.in_(branch_list))

# For ERP service queries:
# Pass branch to erp_service methods that support it
```

### DSM Special Case
`DSM` is not a real branch — it expands to `['20GR', '25BW']` via `expand_branch_filter()`. Always use `expand_branch_filter()` rather than direct equality checks.

### Template Updates
After wiring the data filtering, update kiosk/TV templates to:
1. Remove "Showing all branches" or "Showing all data" notices from branch-filtered views
2. Keep the notice on pick-related views that genuinely can't filter
3. Add a `branch-active-indicator` showing which branch is active (the `kiosk_branch` / `tv_branch` var is already in context)

---

## Task 3: Cleanup the Legacy `warehouse/tv_board.html`

There's a `app/templates/warehouse/tv_board.html` that's a legacy duplicate of `app/templates/tv/tv_board.html`. Check if any route still references it. If not, delete it. If so, update the route to use the `tv/` version.

---

## Task 4: UPLOAD_FOLDER Durability

The app uses local disk storage for uploads (`UPLOAD_FOLDER`). This is not durable across Fly machine replacement. Options:
- Mount a Fly Volume to persist uploads
- Switch to object storage (S3/R2)

Check `app/__init__.py` and config for how `UPLOAD_FOLDER` is set up. Evaluate the simplest fix (likely a Fly Volume mount in `fly.toml`).

---

## Task 5: Smoke Test All Routes

After completing Tasks 2-3, verify that these URLs don't 500-error (you can check by reading the route code for obvious issues — you won't have a running server):
- `/kiosk/20GR/pickers`
- `/kiosk/20GR/work-orders`
- `/tv/20GR/picks`
- `/tv/20GR/board/Door1`
- `/kiosk/DSM/work-orders` (tests DSM expansion)

---

## Architecture Rules
1. **No DB migrations** — pick data can't be filtered, don't add columns
2. **Don't fake branch isolation** — if data can't filter, show a notice, don't filter by something unrelated
3. **Preserve backward compatibility** — all existing URLs must keep working
4. **Use `expand_branch_filter()`** — never do `== branch` when `branch` could be `DSM`
5. **Use CSS custom properties** from `style.css` `:root` — don't hardcode colors/sizes
6. **Branch precedence for shell pages:** URL param > localStorage > session > None
7. **Branch identity for kiosk/TV:** URL path IS the branch. No session, no localStorage.
8. **TRIM joins** — All central_db_mode mirror queries MUST use `TRIM()` on `cust_key` and `seq_num` joins (already done — don't regress)

## Known Pitfalls
1. **Edit tool requires Read first** — always Read files before editing. Batch-read in parallel.
2. **Merge conflicts on push** — `app/__init__.py` and `app/templates/base.html` are hot files. `git fetch origin main-fly && git rebase origin/main-fly` before pushing.
3. **fly.toml has unstaged changes** — don't accidentally stage it.
4. **WorkOrder model** — Check `app/models.py` for the exact `branch_code` column name and any existing filter methods before writing queries.
5. **ERP service** — `app/Services/erp_service.py` has existing branch filtering patterns. Follow them. All mirror queries now use TRIM on cust_key/seq_num — maintain this pattern for any new queries.
6. **Schema drift** — `so_id` and `seq_num` have integer vs varchar drift between mirror tables and ERP source. Always use CAST/TRIM in joins.

## Output Format
When done, provide:
1. Summary of changes (files changed, what was done)
2. Which kiosk/TV routes are now branch-filtered vs still showing all data
3. Any issues found or deferred items
4. Commit and push to `main-fly`

# Agent Handoff — 2026-03-31

## What just shipped (PR open)

**Branch:** `codex/dashboard-stats-integration`
**PR:** https://github.com/amcgrean/WH-Tracker/compare/main...codex/dashboard-stats-integration

Migrated `dashboard_stats` from a single row (id=1) to one row per branch (`system_id TEXT PRIMARY KEY`):
- `models.py` — `DashboardStats.id` replaced with `system_id`
- `picks.py:_read_dashboard_stats(branch)` — now filters/aggregates per branch; DSM = 20GR+25BW
- `sync_erp.py:_update_dashboard_stats()` — groups picks by system_id, upserts per branch; empty handling code now `UNROUTED`
- Migration `o9p0q1r2s3t4_dashboard_stats_per_branch.py` — drop/recreate table

## Pending stash work (NOT yet in a PR)

There is a stash `stash@{0}` on local branch `codex/delivery-reporting-manager-dashboard` (that branch itself was already merged). The stash contains a batch of changes from a previous session that were not committed. They should be applied to a fresh branch off `main` and submitted as a follow-on PR.

To inspect: `git stash show -p stash@{0}`

### Contents of the stash

1. **Auth gating — dispatch + sales blueprints**
   - `app/Routes/dispatch/__init__.py` — adds `before_request` guard redirecting unauthenticated users to login
   - `app/Routes/sales/__init__.py` — same pattern
   - `app/Routes/auth/login.py` — propagates `?next=` URL through the OTP flow so users land back where they were after logging in
   - `app/templates/auth/login.html` — passes `next` param through the form action

2. **`/api/branch-stats` endpoint** (`app/Routes/main/api.py`)
   - New route that reads `dashboard_stats` and returns JSON array of per-branch stats (system_id, open_picks, handling_breakdown, open_work_orders, updated_at)
   - Also updates `/debug/counts` to read from `dashboard_stats` instead of hitting ERP directly

3. **Supervisor dashboard branch stats widget** (`app/templates/supervisor/dashboard.html`)
   - Adds a row of per-branch glass cards that polls `/api/branch-stats` every 30 seconds
   - Shows open picks + handling breakdown badges per branch
   - **BUG**: The JS does `if (data && data.branches) renderBranchStats(data.branches)` but the API returns a plain JSON array, not `{branches: [...]}`. Fix: change to `if (data && Array.isArray(data)) renderBranchStats(data)`

4. **PO cache refresh button** (`app/Routes/po_routes.py`, `app/templates/po/open_pos.html`)
   - New admin-only endpoint `POST /po/api/admin/refresh-cache` that runs `REFRESH MATERIALIZED VIEW CONCURRENTLY public.app_po_header`
   - Adds a "Refresh" button in the PO list header (admin only) that hits this endpoint and reloads the page

### How to apply the stash

```bash
git checkout main && git pull origin main
git checkout -b codex/auth-and-branch-stats
git stash apply stash@{0}
# Fix the JS bug in supervisor/dashboard.html (data.branches -> data)
# Then commit and push
```

## Known caveats / gotchas

- **`open_work_orders` is 0 everywhere** — `wo_header.branch_code` was just added to the ERP sync; existing rows backfill as they get touched. Don't surface per-branch WO counts in the UI until data is confirmed populated.
- **AUTH_REQUIRED is still `false`** — auth gating for dispatch/sales/main routes is not enforced in production yet. Once the stash PR is merged and users are seeded, flip with: `fly secrets set AUTH_REQUIRED=true --app wh-tracker-fly`
- The `main_bp` routes (picks, kiosk, TV, etc.) do NOT yet have `before_request` auth guards — only dispatch and sales are in the stash. Kiosk/TV routes should remain permanently exempt.

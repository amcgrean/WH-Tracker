# Next Agent Handoff — 2026-03-27

## Current State

### UI/UX Overhaul — COMPLETE (Phases 0-7)
All 8 phases of the frontend architecture overhaul are now complete. The full spec is in `docs/phase 1 audit.md`.

**Commit history:**
- `a000083` — Phases 0-4: Foundation, global branch filter, kiosk/TV shells, dispatch mobile
- `94ba468` — Phases 5-7: Supervisor/warehouse consistency, sales polish, legacy refresh + PWA

### What Was Done This Session (Phases 5-7)

#### Phase 5: Supervisor + Warehouse Consistency
- **wo_board.html** — Extracted inline styles to shared CSS classes (`so-card-ops`, `status-badge-ops`, `dept-badge-ops`). Added mobile card layout with responsive breakpoint. Modal updated with design system styling.
- **supervisor/dashboard.html** — Responsive polish: stacked columns on phone, consistent glass-card usage, `card-header-ops` for section headers.
- **picks_board.html** — Shared CSS classes (`handling-section-ops`, `wh-card`, `action-btn-ops`, `line-badge-ops`). Added `branch-all-indicator` ("Showing all branches") since pick data has no `branch_code`.
- **order_board.html** — Same treatment as picks_board. Glass-card empty state.
- **select_handling.html** — Kiosk-style `handling-grid__btn` buttons with gradient backgrounds and icons.
- **view_picks.html** — Glass-card layout, `big-checkbox-ops` class, `table-warehouse` for vertical alignment.
- **pick_detail.html** — Glass-card + `card-header-ops`, `code-pill-ops` for handling codes.

#### Phase 6: Sales Visual Consistency
All 6 sales pages aligned with glassmorphic design system from `hub.html`:
- **customer_profile.html** — Glass-card KPI tiles, award placeholder, account details, tables
- **customer_notes.html** — Glass-card form + timeline layout
- **customer_statement.html** — Glass-card AR summary, open/invoiced order tables
- **products.html** — Glass-card search bar (rounded-pill), product grid
- **awards.html** — Glass-card tier legend, customer activity table with design tokens
- **rep_dashboard.html** — Glass-card KPIs, period buttons using `btn-ops-primary`, progress bars with CSS vars

#### Phase 7: Cleanup + PWA
- **dashboard.html** — Full refresh: `legacy-stat-card` for KPIs, glass-card tables, auto-refresh badge
- **admin.html** — Glass-card form + table, `admin-row` hover, design system modals
- **pickers_picks.html** — Glass-card summary stats, split table layout
- **picker_details.html** — Breadcrumb, glass-card DataTable, moved CSS to `<head>`
- **picker_stats.html** — Period button group, glass-card overview tiles, sortable stats table
- **manifest.json** — PWA manifest: name "Beisser OPS", theme `#004526`, standalone display
- **service-worker.js** — Shell asset caching (CSS, JS, fonts). No data caching.
- **base.html** — Added `<link rel="manifest">`, `<meta name="theme-color">`, SW registration script

### CSS Design System Additions (`style.css`)
New shared classes added:
- `.card-header-ops` — Green gradient header for card sections
- `.so-card-ops`, `.wo-row` — Supervisor WO board card system
- `.status-badge-ops`, `.dept-badge-ops` — Status/department badges
- `.handling-section-ops` — Warehouse handling code grouping
- `.wh-card`, `.status-indicator` — Warehouse card with left color bar
- `.action-btn-ops` — Circular action buttons
- `.line-badge-ops`, `.line-count-badge-ops`, `.code-pill-ops` — Item count badges
- `.handling-grid`, `.handling-grid__btn` — Kiosk-style 2x2 button grid
- `.big-checkbox-ops`, `.table-warehouse` — Large checkboxes and table alignment
- `.branch-all-indicator` — "Showing all branches" indicator
- `.legacy-stat-card` — Refreshed stat card for legacy pages
- `.admin-row` — Admin table hover
- `.period-btn-group` — Period selector button group

---

### Bug Fix: Blank Customer Names/Addresses (commit `9c86671`)

**Root cause:** PR #69 (commit `697c13e`) applied `TRIM()` to `cust_key` and `seq_num` joins in only 2 methods (`get_so_header` and `get_dispatch_stops`). The remaining 10 central_db_mode PostgreSQL mirror queries still used bare `c.cust_key = soh.cust_key` comparisons. When ERP-synced key fields had trailing whitespace, LEFT JOINs silently failed — returning NULL for `cust_name`, `address_1`, `city`, etc.

**Fix:** Applied `TRIM()` consistently to all 12 mirror-table customer/ship-to joins across `erp_service.py`:
- `get_todays_picks()` — picks board
- `get_order_board()` — order board
- `get_staged_orders()` — staged orders view
- `_get_sales_rep_metrics_inner()` — sales rep dashboard
- `get_sales_orders()` (two variants) — sales order lists
- `get_recent_invoices()` — invoice history
- `get_sales_dashboard_data()` — top customers widget
- `get_work_orders()` — work order board
- `get_sales_delivery_tracker()` — delivery tracker (the primary reported symptom)

Pattern used: `TRIM(c.cust_key) = TRIM(soh.cust_key)` and `TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))`

SQL Server legacy-path queries were NOT changed — they use different type handling (TRY_CAST, nvarchar) and are unaffected by this issue.

---

## Fly Deployment
- App: `wh-tracker-fly` on Fly.io (`ord` region)
- Status: **running and healthy**
- Machine size: `shared-cpu-1x@512MB`
- Vercel remains the active production path; Fly is validated and ready for cutover

### Database (Supabase — project `vyatosniqboeqzadyqmr`)
- `alembic_version`: `c1d2e3f4a5b6 (head)` — single clean head
- Schema drift on `so_id`/`seq_num` integer vs varchar — handled via CAST in erp_service.py

---

## Deferred / Follow-up Items

### Must-do before cutover
1. **PWA icons** — 192x192 and 512x512 PNG icons need to be created and placed in `app/static/icons/`
2. **Kiosk/TV branch-aware data filtering** — Routes exist but data shows all branches with notice (Phase 2/3 partial)
3. **UPLOAD_FOLDER** — Uses local disk storage, not durable across machine replacement. Needs Fly Volume or object storage.

### Nice-to-have
4. **Pick module branch migration** — Add `branch_code` to Pickster, Pick, PickAssignment, WorkOrderAssignment (DB migration required, out of scope for UI pass)
5. **Schema drift cleanup** — ALTER COLUMN `erp_mirror_so_detail.so_id` and `erp_mirror_cust_shipto.seq_num` to varchar if safe
6. ~~**Customer query fix**~~ — **DONE** (commit `9c86671`). TRIM fix applied to all 12 central_db_mode mirror queries, not just the 2 from PR #69.

### Branch status
- `main-fly` is ahead of `main` — ready for PR/merge when user is ready for production cutover

---

## Key Files

| File | Purpose |
|------|---------|
| `app/static/css/style.css` | Global design system with all shared CSS classes |
| `app/static/manifest.json` | PWA manifest |
| `app/static/service-worker.js` | Shell asset caching service worker |
| `app/branch_utils.py` | Branch constants, normalization, DSM expansion |
| `app/templates/base.html` | Shell: sidebar, branch selector, search, PWA registration |
| `app/templates/kiosk_base.html` | Kiosk standalone shell |
| `app/templates/tv_base.html` | TV standalone shell |
| `docs/phase 1 audit.md` | Full UI/UX overhaul specification |

---

## Quick Health Check Commands

```bash
# Fly app health
curl -fsS https://wh-tracker-fly.fly.dev/healthz
curl -fsS https://wh-tracker-fly.fly.dev/dispatch/api/health

# Migration head
flyctl ssh console --app wh-tracker-fly -C "sh -c 'cd /app && flask db current'"
# Expected: c1d2e3f4a5b6 (head)
```

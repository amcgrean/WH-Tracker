Good catch — this significantly changes the kiosk and TV architecture. Here is the revised audit with those sections updated.

Updated Frontend Architecture Audit & Implementation Plan (Rev 2)
Key Change from Rev 1
Picker, work order, and TV pages must be per-branch kiosk instances — each physical location (20GR, 25BW, 40CV, 10FD) runs its own kiosk showing only that branch's pickers / door builders / orders. These should be standalone pages (like tv_board.html and delivery/map.html), not wrapped in the sidebar shell.

Additionally: the pick module currently has zero branch filtering anywhere — Pickster, Pick, PickAssignment, and WorkOrderAssignment models all lack a branch_code field. This is flagged as a future fix item.

1. Route / Page Inventory by Category
A. Shared Layout & Core
File	Type	Description
app/templates/base.html	Layout	Shared shell: sidebar, topbar, global search, glassmorphic design
app/static/css/style.css	CSS	Design system: tokens, glass components, app shell, responsive breakpoints
app/static/js/app.js	JS	Sidebar toggle, AJAX helper, picker button delegation
app/navigation.py	Python	Role-based nav sections & items, active-state detection
B. Dispatch (dense operations workspace)
File	Route	Description
app/templates/dispatch/index.html	GET /dispatch/	Dispatch console: 3-col CSS grid, Leaflet map, order table, detail panel
app/static/dispatch/demo.js	—	Console state: filtering, sorting, search, auto-refresh, detail panel, manifest PDF
app/static/dispatch/vehicles.js	—	Vehicle overlay: SVG truck icons, live Samsara polling, branch legend
app/Routes/dispatch_routes.py	7 endpoints	/dispatch/, /api/stops, /api/branches, /api/manifest, /api/vehicles/live
app/Services/dispatch_service.py	—	Stops query, manifest PDF, GPS CSV, branch choices
C. Delivery (desktop/mobile responsive + standalone map)
File	Route	Description
app/templates/delivery/board.html	GET /delivery	KPI cards, fleet telemetry table, shipments; extends base.html
app/templates/delivery/map.html	GET /delivery/map[/<branch>]	Standalone full-screen Leaflet map, dark theme
app/templates/delivery/detail.html	GET /delivery/detail/<so_number>	Order detail + timeline; extends base.html
D. Warehouse
File	Route	Description
app/templates/warehouse/picks_board.html	GET /warehouse/board	Grouped cards by handling code; extends base.html
app/templates/warehouse/tv_board.html	GET /warehouse/board/tv/<handling_code>	Standalone dark TV display, 30s refresh
app/templates/warehouse/order_board.html	GET /warehouse/board/orders	Card grid with grouping toggle; extends base.html
app/templates/warehouse/select_handling.html	GET /warehouse	2x2 button grid; extends base.html
app/templates/warehouse/view_picks.html	GET /warehouse/detail/<so_number>	SO-grouped pick tables; extends base.html
app/templates/warehouse/pick_detail.html	GET /warehouse/wh-detail/<so_number>	Customer + line items; extends base.html
E. Sales
File	Route	Branch Filter?	Description
app/templates/sales/hub.html	GET /sales/hub	No	Glass-card feature hub
app/templates/sales/rep_dashboard.html	GET /sales/rep-dashboard	No	Rep KPIs, period toggle
app/templates/sales/order_status.html	GET /sales/order-status	Yes (query param)	Live search + branch dropdown
app/templates/sales/order_history.html	GET /sales/order-history	Yes (query param)	Filter form + paginated table
app/templates/sales/invoice_lookup.html	GET /sales/invoice-lookup	Yes (query param)	Search with branch + status + date
app/templates/sales/reports.html	GET /sales/reports	Yes (query param)	Chart.js, period + branch selectors
app/templates/sales/delivery_tracker.html	GET /sales/tracker	Yes (button group)	Branch buttons, AJAX polling
app/templates/sales/customer_profile.html	GET /sales/customer-profile/<num>	No	Customer detail
app/templates/sales/customer_notes.html	GET /sales/customer-notes/<num>	No	Notes CRUD
app/templates/sales/customer_statement.html	GET /sales/customer-statement/<num>	No	AR statement
app/templates/sales/products.html	GET /sales/products	No	Product catalog
app/templates/sales/awards.html	GET /sales/awards	No	Awards / loyalty tiers
F. Supervisor (desktop + mobile)
File	Route	Description
app/templates/supervisor/dashboard.html	GET /supervisor/dashboard	3-col glass layout; extends base.html
app/templates/supervisor/wo_board.html	GET /supervisor/work_orders	SO-grouped WO cards with bulk assign; extends base.html
G. Picker Flow (per-branch standalone kiosk)
File	Route	Extends base?	Description
app/templates/index.html	GET /	Yes (hides sidebar via kiosk mode)	Picker selection grid, 120s refresh
app/templates/confirm_picker.html	GET /confirm_picker/<id>	Yes	Confirmation form
app/templates/input_pick.html	GET /input_pick/<id>/<type_id>	Yes	Barcode input form
app/templates/complete_pick.html	GET /complete_pick/<pick_id>	Yes	Pick completion
Current branch scoping: NONE. Pickster model has no branch_code. All pickers shown globally.

H. Work Order Flow (per-branch standalone kiosk)
File	Route	Extends base?	Description
app/templates/work_order/user_selection.html	GET /work_orders	Yes	Button grid for user (door builder) selection
app/templates/work_order/open_orders.html	GET /work_orders/open/<user_id>	Yes	Table of open WOs
app/templates/work_order/select_orders.html	GET /work_orders/select	Yes	Checkbox table for WO selection
app/templates/work_order/scan_barcode.html	GET /work_orders/scan/<user_id>	Yes	Large barcode input
Current branch scoping: NONE. WorkOrderAssignment has no branch_code. WorkOrder (ERP mirror) HAS branch_code but it's never used for filtering.

I. TV / Passive Display (per-branch standalone)
File	Route	Extends base?	Description
app/templates/open_picks.html	GET /pick_tracker	Yes	Open picks by handling code
app/templates/warehouse/tv_board.html	GET /warehouse/board/tv/<code>	No (standalone)	Dark theme, large text, 30s refresh
app/templates/delivery/map.html	GET /delivery/map	No (standalone)	Full-screen dark Leaflet map
Current branch scoping: NONE on pick/warehouse TV pages. Delivery map has branch via URL path.

J–L. (Hub, Auth, Credits, Other — unchanged from Rev 1)
2. Current-State Assessment
Pages Already Aligned with Shared Shell
sales/hub.html — best example of target aesthetic
supervisor/dashboard.html — glass cards, animations, status pills
delivery/board.html — KPI cards, table-ops
delivery/detail.html — glass cards, timeline
dispatch/index.html — dense but uses shared shell correctly
Pages That Are Legacy / Misaligned
Same as Rev 1 — work order pages (900px fixed width, inline styles), picker input/confirm/complete (minimal), various stats pages.

NEW: Pages That Should Become Standalone Per-Branch Kiosk
These currently extend base.html but should be standalone (no sidebar, no topbar), served at per-branch URLs, showing only that branch's data:

Page	Current	Target
index.html (picker selection)	Extends base, hides sidebar via CSS hack	Standalone per-branch kiosk
confirm_picker.html	Extends base	Standalone kiosk (inherits branch from flow)
input_pick.html	Extends base	Standalone kiosk (inherits branch from flow)
complete_pick.html	Extends base	Standalone kiosk (inherits branch from flow)
work_order/user_selection.html	Extends base	Standalone per-branch kiosk
work_order/open_orders.html	Extends base	Standalone kiosk (inherits branch from flow)
work_order/select_orders.html	Extends base	Standalone kiosk (inherits branch from flow)
work_order/scan_barcode.html	Extends base	Standalone kiosk (inherits branch from flow)
open_picks.html (TV)	Extends base	Standalone per-branch TV display
Branch Scoping Gap in Pick Module
No model in the pick/WO system has branch awareness:

Model	Has branch_code?	Notes
Pickster	No	Pickers are global, not branch-scoped
Pick	No	Individual picks have no branch
PickAssignment	No	SO assignments have no branch
WorkOrder (ERP mirror)	Yes	Has branch_code but never filtered on
WorkOrderAssignment	No	Local assignment tracking, no branch
Future fix required: Add branch_code to Pickster, Pick, PickAssignment, and WorkOrderAssignment. Migrate existing data. Filter all queries by branch. This is a backend data model change and is noted but out of scope for this UI/UX pass.

3. Branch Filter Architecture Proposal
3.1 Two Separate Branch Concepts
The audit reveals two distinct branch filtering needs:

Context	Mechanism	Scope
Sidebar global filter	Session-stored selection in sidebar dropdown	Sales, warehouse (supervisor views), dispatch, delivery pages
Kiosk branch identity	URL path segment (/kiosk/20GR/...)	Picker flow, WO flow, TV displays — the kiosk "is" a specific branch
These are architecturally different. The sidebar filter is a user preference. The kiosk branch is a physical deployment identity.

3.2 Sidebar Global Filter (for shell pages)
Canonical state: session['selected_branch']

Precedence:

Explicit URL/query param (?branch=20GR) — wins always
Session value (session['selected_branch']) — stored user selection
Default: None (no filter / all branches)
Persistence: Server-side session via POST /api/set-branch

Template context: @app.context_processor injects selected_branch and branch_choices into every page.

Branch choices (sidebar dropdown):

Value	Label	Expansion
(empty)	All Branches	No filter
20GR	Grimes	['20GR']
25BW	Birchwood	['25BW']
40CV	Coralville	['40CV']
10FD	Fort Dodge	['10FD']
DSM	Des Moines Area	['20GR', '25BW']
DSM expansion: centralized in one utility function (currently duplicated between ERPService._expand_branch_filters() and dispatch's GRIMES_AREA logic).

Affected pages (read global branch):

sales/order_status.html — remove local dropdown
sales/order_history.html — remove local dropdown
sales/invoice_lookup.html — remove local dropdown
sales/reports.html — remove local dropdown + onchange
sales/delivery_tracker.html — remove branch button group
delivery/board.html — add branch filtering (currently none)
warehouse/picks_board.html — add if data is branch-scoped
warehouse/order_board.html — add if data is branch-scoped
Dispatch special case: reads global on page load as initial value, retains local dropdown for rapid switching within console. Does NOT write back to session.

3.3 Kiosk Branch Identity (for standalone pages)
Mechanism: branch is part of the URL path, e.g.:

/kiosk/20GR/pickers — picker selection for Grimes
/kiosk/25BW/pickers — picker selection for Birchwood
/kiosk/20GR/work-orders — WO user selection for Grimes
/kiosk/20GR/pick-tracker — open picks TV for Grimes
/warehouse/board/tv/20GR/<handling_code> — TV board for Grimes
No session, no sidebar: the kiosk URL IS the branch identity. The physical kiosk's browser bookmark determines which branch it shows.

Route pattern: @main.route('/kiosk/<branch>/pickers') — branch passed through the entire flow via URL segments or hidden form fields.

Backward compatibility: existing non-branched routes (/, /work_orders, /pick_tracker) continue to work and show all-branch data (useful for supervisor/admin views). New per-branch kiosk routes are additive.

3.4 Backward Compatibility
Existing URL params (?branch=20GR) still win over session
Existing non-branched kiosk URLs continue to work (show all data)
Per-branch kiosk URLs are new additions, not replacements
GRIMES_AREA in dispatch maps to DSM in the global system
4. Dispatch Redesign Proposal
(Unchanged from Rev 1)

4.1 Desktop Structure
Current 3-column CSS grid (420px sidebar | 6px divider | map) is solid
Polish independent scrolling: sidebar .gridwrap gets overflow-y: auto; height: calc(100vh - topbar)
Sticky search at top of sidebar
Detail panel slide-in from right (already exists)
4.2 Mobile / Tablet Layout
Tabbed layout at < 1200px: "Orders" | "Map" | "Details"
Orders tab: full-width scrollable list with all filters
Map tab: full-screen map with floating branch chip
Details tab: full-screen detail (replaces slide-in panel)
Tab state in sessionStorage
At < 768px: larger touch targets, stacked address rows, bottom-sheet actions
4.3 Key Files
File	Change
dispatch/index.html	Add mobile tab nav (d-xl-none), sticky search, read global branch on load
dispatch/demo.js	Tab switching logic, touch-friendly detail panel
style.css	Dispatch mobile tab styles
5. Page-Type-Specific UI Plan
5.1 Kiosk Pages — Per-Branch Standalone (picker + work order flows)
Affected pages: index.html, confirm_picker.html, input_pick.html, complete_pick.html, work_order/user_selection.html, work_order/open_orders.html, work_order/select_orders.html, work_order/scan_barcode.html

Architecture:

Create a kiosk_base.html standalone template (no sidebar, no topbar, no base.html inheritance)

Full-screen content area
Branch identity header (e.g., "GRIMES — Picker Station")
Large base font (18px+), minimum 48px tap targets
Auto-refresh where appropriate
Shared kiosk CSS section in style.css
Optional: subtle branding bar at top with branch name + clock
All kiosk pages extend kiosk_base.html instead of base.html

New URL routes (additive — old routes stay):

Route	Template	Description
GET /kiosk/<branch>/pickers	index.html	Picker selection for branch
GET /kiosk/<branch>/confirm/<picker_id>	confirm_picker.html	Confirm picker
GET /kiosk/<branch>/pick/<picker_id>/<type_id>	input_pick.html	Barcode input
GET /kiosk/<branch>/complete/<pick_id>	complete_pick.html	Complete pick
GET /kiosk/<branch>/work-orders	user_selection.html	Door builder selection for branch
GET /kiosk/<branch>/work-orders/open/<user_id>	open_orders.html	Open WOs for branch
GET /kiosk/<branch>/work-orders/select	select_orders.html	Select WOs
GET /kiosk/<branch>/work-orders/scan/<user_id>	scan_barcode.html	Barcode scan
Branch filtering in queries (interim before full pick module fix):

Picker selection: filter Pickster by branch. Requires branch_code on Pickster model (future fix) OR a simpler interim: maintain a config mapping of picker IDs to branches.
Work order user selection: filter door builders by branch (same constraint).
Work order open/select: WorkOrder already has branch_code — filter WO queries by it.
Open picks / TV: filter picks by branch where possible via ERP mirror data joins.
Future fix (out of scope for this pass): Add branch_code to Pickster, Pick, PickAssignment, WorkOrderAssignment models. Migrate existing data. Make all pick module queries branch-aware.

Interim approach: For this UI/UX pass, create the per-branch kiosk URL structure and standalone templates. Branch filtering in the actual data queries will initially show all data (same as today) unless WorkOrder.branch_code allows filtering (work orders can be filtered immediately). Picker filtering requires the model migration and is noted as a fast-follow.

5.2 TV Pages — Per-Branch Standalone
Affected: open_picks.html, warehouse/tv_board.html

Architecture:

Create per-branch TV routes:
GET /tv/<branch>/picks — open picks for branch
GET /tv/<branch>/board/<handling_code> — TV board for branch
GET /tv/<branch>/work-orders — open work orders TV for branch (new)
All TV pages are standalone (no base.html)
Shared dark TV theme in style.css (extracted from tv_board.html's inline styles)
Auto-refresh (30s meta tag or JS interval)
Large text, high contrast, bold status hierarchy
Branch identity in header/corner
open_picks.html currently extends base.html — convert to standalone TV template for per-branch use. Keep the existing base.html version at /pick_tracker for supervisor/admin desktop use.

5.3 Supervisor Pages (desktop + mobile)
(Unchanged from Rev 1)

dashboard.html: minor polish, stack columns on phone
wo_board.html: extract inline styles, card-style WO rows on mobile, full-screen modal on mobile
Wire into global branch filter if supervisor needs to switch between branches
5.4 Warehouse Pages
(Unchanged from Rev 1)

Extract shared warehouse card patterns to style.css
Wire picks_board.html and order_board.html into global branch filter where data supports it
select_handling.html: shared kiosk button class
view_picks.html / pick_detail.html: shared large-checkbox / table styles
5.5 Sales Pages
(Unchanged from Rev 1)

Preserve hub.html as visual reference
Remove per-page branch dropdowns, replace with global sidebar reading
Add "Filtering by: [Branch]" indicator
Extract inline styles for consistency
6. File-by-File Change Plan
Phase 0: Foundation
File	Changes
app/__init__.py	Add context_processor for selected_branch / branch_choices. Add POST /api/set-branch route.
app/templates/base.html	Add branch dropdown to sidebar. Add {% block body_class %} mechanism. Wire dropdown to /api/set-branch.
app/templates/kiosk_base.html (new)	Standalone kiosk shell: no sidebar, branch header, large font, clock, auto-refresh block.
app/templates/tv_base.html (new)	Standalone TV shell: dark theme, no chrome, large font, auto-refresh, branch identity.
app/static/css/style.css	Add: kiosk mode styles, TV dark theme (extracted from tv_board inline), dispatch mobile tabs, shared component classes (kiosk buttons, kiosk inputs, kiosk tables, TV status badges).
app/static/js/app.js	Add: branch dropdown change handler.
app/Services/erp_service.py	Centralize DSM expansion in one utility.
app/Services/dispatch_service.py	Remove duplicate GRIMES_AREA expansion; use shared utility.
Phase 1: Global Sidebar Branch Filter
File	Changes
app/Routes/sales_routes.py	Each branch-aware route: branch = request.args.get('branch') or session.get('selected_branch')
app/Routes/routes.py	Same for delivery/tracker routes.
app/Routes/dispatch_routes.py	Read global branch as default for /api/stops and /api/vehicles/live.
app/templates/sales/order_status.html	Remove local dropdown. Add "Filtering by: X" indicator.
app/templates/sales/order_history.html	Remove local dropdown.
app/templates/sales/invoice_lookup.html	Remove local dropdown.
app/templates/sales/reports.html	Remove local dropdown + onchange.
app/templates/sales/delivery_tracker.html	Remove branch button group.
app/templates/dispatch/index.html	Initialize branch from global selected_branch.
Phase 2: Per-Branch Kiosk Pages
File	Changes
app/Routes/routes.py	Add kiosk routes: /kiosk/<branch>/pickers, /kiosk/<branch>/confirm/<id>, /kiosk/<branch>/pick/<id>/<type_id>, /kiosk/<branch>/complete/<id>, /kiosk/<branch>/work-orders, /kiosk/<branch>/work-orders/open/<user_id>, /kiosk/<branch>/work-orders/select, /kiosk/<branch>/work-orders/scan/<user_id>. Each passes branch to template.
app/templates/index.html	Refactor to extend kiosk_base.html. Extract inline kiosk CSS to style.css. Accept branch context.
app/templates/confirm_picker.html	Extend kiosk_base.html. Large touch targets. Carry branch through links/forms.
app/templates/input_pick.html	Extend kiosk_base.html. Large input + button. Scanner-first UX.
app/templates/complete_pick.html	Extend kiosk_base.html. Clear success/next-action.
app/templates/work_order/user_selection.html	Extend kiosk_base.html. Large button grid. Accept branch.
app/templates/work_order/open_orders.html	Extend kiosk_base.html. Remove 900px fixed width. Fluid kiosk table.
app/templates/work_order/select_orders.html	Extend kiosk_base.html. Same. Larger checkboxes.
app/templates/work_order/scan_barcode.html	Extend kiosk_base.html. Already partially kiosk — normalize.
Phase 3: Per-Branch TV Pages
File	Changes
app/Routes/routes.py	Add TV routes: /tv/<branch>/picks, /tv/<branch>/work-orders.
app/templates/open_picks.html	Create TV variant extending tv_base.html. Keep existing base.html version for desktop.
app/templates/warehouse/tv_board.html	Refactor to extend tv_base.html. Extract inline dark CSS. Add branch route param.
app/static/css/style.css	Shared TV dark theme tokens and status badge hierarchy.
Phase 4: Dispatch Desktop + Mobile
File	Changes
app/templates/dispatch/index.html	Add mobile tab nav (d-xl-none). Sticky search. Confirm scroll independence.
app/static/dispatch/demo.js	Tab switching, touch-friendly detail panel.
app/static/css/style.css	Dispatch mobile tab and responsive styles.
Phase 5: Supervisor + Warehouse Consistency
File	Changes
app/templates/supervisor/wo_board.html	Extract inline styles. Mobile card layout. Full-screen mobile modal.
app/templates/supervisor/dashboard.html	Minor responsive polish.
app/templates/warehouse/picks_board.html	Extract inline styles. Wire global branch if applicable.
app/templates/warehouse/order_board.html	Extract inline styles. Wire global branch if applicable.
app/templates/warehouse/select_handling.html	Shared kiosk button class.
app/templates/warehouse/view_picks.html	Extract inline styles. Shared large-checkbox.
app/templates/warehouse/pick_detail.html	Minor alignment.
Phase 6: Sales Visual Consistency
File	Changes
app/templates/sales/customer_profile.html	Extract inline styles. Glass-card alignment.
app/templates/sales/customer_notes.html	Extract inline styles.
app/templates/sales/customer_statement.html	Extract inline styles.
app/templates/sales/products.html	Extract inline styles.
app/templates/sales/awards.html	Extract inline styles.
app/templates/sales/rep_dashboard.html	Minor alignment.
Phase 7: Remaining Cleanup + PWA
File	Changes
app/templates/dashboard.html	Refresh or deprecate.
app/templates/admin.html	Light refresh.
app/templates/pickers_picks.html	Extract inline styles.
app/templates/picker_details.html	Extract inline styles.
app/templates/picker_stats.html	Extract inline styles.
app/static/manifest.json (new)	PWA manifest: name, icons, theme-color (#004526), display: standalone.
app/static/service-worker.js (new)	Cache shell assets only (CSS, JS, fonts). No data caching.
app/templates/base.html	Add <link rel="manifest">, <meta name="theme-color">, SW registration.
7. Risks / Unknowns / Assumptions
Risks
Risk	Mitigation
Picker model has no branch_code — kiosk pages can't filter pickers by branch until model is migrated	Phase 2 creates the URL structure and standalone templates. Filtering shows all pickers initially. Fast-follow adds branch_code to Pickster and filters queries.
WorkOrderAssignment has no branch_code — but WorkOrder (ERP mirror) does	Join through WorkOrder.branch_code for WO filtering. Assignment-level filtering deferred to model migration.
Removing per-page branch filters may confuse users	Add "Filtering by: [Branch]" indicator on each affected page
Dispatch local vs global branch state conflict	Dispatch reads global on load, does NOT write back
TV open_picks currently extends base.html — splitting into TV variant creates two templates for one concept	Clear naming: open_picks.html = desktop/supervisor view, tv/picks.html = TV display view
32 templates with inline styles — extraction risks visual regressions	Incremental per-phase, visual check each page
Unknowns
Unknown	Impact
How to assign pickers to branches without branch_code on Pickster	Future fix: add field + admin UI to assign pickers to branches. Interim: config mapping or convention.
Whether warehouse picks_board/order_board data is branch-scoped in queries	Need to verify ERP mirror queries. If not, leave unfiltered until pick module fix.
Whether DSM label is familiar to users vs "Des Moines Area" or "Grimes Area"	Confirm naming. Propose: value=DSM, label="Des Moines Area".
Whether existing non-branched kiosk URLs should redirect or just coexist	Recommend: coexist. Non-branched shows all (admin/supervisor use).
Assumptions
Auth pages remain separate from shared shell
delivery/map.html stays standalone (intentional)
Backend business logic unchanged except branch propagation
No new database migrations in this UI pass (model changes are future fix)
GRIMES_AREA in dispatch ≡ DSM in sidebar
Existing non-branched routes remain functional alongside new per-branch routes
Future Fix: Pick Module Branch Awareness
Tracked separately. Required changes (out of scope for this pass):

Add branch_code (indexed, nullable) to: Pickster, Pick, PickAssignment, WorkOrderAssignment
Database migration
Admin UI or bulk tool to assign existing pickers/builders to branches
Update all picker/WO queries to filter by branch_code
Update per-branch kiosk routes to actually filter data
Update TV routes to filter by branch
Update statistics/reporting pages to support branch-scoped views
8. Recommended Implementation Order
Phase	Scope	Effort	Dependencies	Notes
0. Foundation	Branch context processor, sidebar dropdown, kiosk_base.html, tv_base.html, shared CSS classes, DSM centralization	Medium	None	Unblocks everything
1. Global Branch Filter	Wire sales + dispatch + delivery to global branch, remove per-page dropdowns	Medium	Phase 0	Immediate user-facing improvement
2. Per-Branch Kiosk Pages	New /kiosk/<branch>/... routes, standalone picker + WO templates	Medium-High	Phase 0	URL structure ready even before data filtering works
3. Per-Branch TV Pages	New /tv/<branch>/... routes, standalone TV templates, dark theme extraction	Low-Medium	Phase 0	Can parallel with Phase 2
4. Dispatch Desktop + Mobile	Independent scroll, sticky search, mobile tab nav	Medium	Phase 0	Can parallel with Phases 2-3
5. Supervisor + Warehouse	Inline style extraction, mobile improvements, branch wiring where applicable	Medium	Phase 1	
6. Sales Consistency	Inline style extraction, design alignment	Low-Medium	Phase 1	
7. Cleanup + PWA	Legacy pages, manifest, lightweight service worker	Low	Phase 0	Lowest priority
Future	Pick module branch_code migration (Pickster, Pick, PickAssignment, WorkOrderAssignment)	High	Phase 2 routes in place	Separate tracked effort
Parallelism: After Phase 0, Phases 1–4 can run concurrently (they touch independent file sets). Phases 5–6 depend on Phase 1 (need global branch in place). Phase 7 is independent.

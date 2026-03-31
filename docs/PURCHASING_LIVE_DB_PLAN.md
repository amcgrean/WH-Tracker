# Purchasing Module Plan Aligned To Live Supabase Mirror

Last updated: 2026-03-31

## Summary

This document replaces the earlier idealized purchasing gameplan assumptions with the real live Supabase shape.

Phase 1 must work against the purchasing data that already exists today:

- `erp_mirror_po_header`
- `erp_mirror_po_detail`
- `erp_mirror_receiving_header`
- `erp_mirror_receiving_detail`
- `erp_mirror_item`
- `erp_mirror_item_branch`
- `erp_mirror_item_uomconv`
- `erp_mirror_wo_header`
- `app_po_header` materialized view
- `app_po_search` view
- `app_po_detail` view
- `app_po_receiving_summary` view
- `po_submissions`

Important live constraints:

- Treat `erp_mirror_po_header.system_id` as the branch key for now.
- Do not assume a separate `branch_code` exists on live PO headers.
- Keep ERP state separate from app-owned workflow and collaboration state.
- Do not assume ERP write-back in Phase 1.
- Keep using Flask + server-rendered templates + Bootstrap.

## Live Read-Model Assumptions

### Existing live objects to use now

#### `app_po_header` materialized view

Use this as the primary Phase 1 PO header read model.

Assumptions:

- One row per PO
- Includes `po_number`
- Includes `system_id` and that is the branch scope
- Includes supplier and status fields already enriched enough for a command-center/listing experience
- Includes cost totals needed for open-spend summary

Compatibility note:

- This is a **materialized view**, not a normal view.
- Any “refresh” UI or sync-support action must treat it as a materialized object.
- Do not add logic that assumes updates are immediately visible unless refresh cadence is known.

#### `app_po_search` view

Use this as the Phase 1 search/list source for:

- open PO listing
- branch-scoped PO queues
- overdue PO detection
- supplier-facing PO searches

Assumptions:

- branch scope comes from `system_id`
- do not require `branch_code`
- do not require supplier geo enrichment yet

#### `app_po_detail` view

Use this as the line workspace source for:

- line status
- ordered / received / open quantities
- expected dates if present
- source-linked line context if present

Do not require supplier-part enrichment for Phase 1.

#### `app_po_receiving_summary` view

Use this as the receiving rollup source for:

- receipt counts
- last receiving timestamp if available
- aggregate quantity/cost mismatch indicators if already modeled

If summary fields are sparse, the UI should still render and fall back to:

- `receipt_count`
- “No receiving summary available”

### ERP mirror tables to use directly in Phase 1 where helpful

#### `erp_mirror_po_header`

Primary ERP branch-scoped PO source.

Use:

- `system_id` as branch key
- PO status and date validation
- direct reconciliation with `app_po_header`

Do not assume `branch_code`.

#### `erp_mirror_po_detail`

Use for:

- validating line-level counts against `app_po_detail`
- future detail enrichment if `app_po_detail` needs backfill

#### `erp_mirror_receiving_header` and `erp_mirror_receiving_detail`

Use for:

- receiving-session visibility
- mismatch detection
- receiving exception generation

Because `receiving_status` is not live yet, receiving lifecycle state should be inferred from:

- PO status
- receiving counts
- known receiving rows
- app-side exception events

#### `erp_mirror_item`, `erp_mirror_item_branch`, `erp_mirror_item_uomconv`

Use only as supporting enrichment in Phase 1:

- item labels
- UOM display normalization
- branch inventory context where already available

Do not block the PO workflow if item-branch or UOM enrichment is missing.

### Mirrors planned soon but not reliable for Phase 1

These should be treated as optional future enrichments:

- `erp_mirror_item_supplier`
- `erp_mirror_supplier_dim`
- `erp_mirror_suppname`
- `erp_mirror_supp_ship_from`
- `erp_mirror_ppo_header`
- `erp_mirror_ppo_detail`
- `erp_mirror_purchase_type`
- `erp_mirror_purchase_costs`
- `erp_mirror_param_po`
- `erp_mirror_param_po_cost`
- `erp_mirror_receiving_status`

The code and UI should gracefully improve when these arrive, but Phase 1 must not depend on them existing.

## Proposed App-Owned Tables

These are app-owned operational tables. They should be migrated by the Flask app and must not be mixed into ERP mirror ownership.

### 1. `purchasing_work_queue`

Purpose:

- normalized action queue for buyers and manager
- stores app workflow state, not ERP source truth

Columns:

- `id` bigint/integer PK
- `queue_type` text not null
  - examples: `overdue_po`, `receiving_checkin`, `receiving_discrepancy`, `suggested_buy_review`, `supplier_followup`, `approval_required`
- `reference_type` text not null
  - examples: `po`, `submission`, `receiving`, `suggested_po`
- `reference_number` text not null
- `po_number` text nullable
- `system_id` text nullable
- `buyer_user_id` int nullable FK `app_users.id`
- `supplier_key` text nullable
- `supplier_name` text nullable
- `title` text not null
- `description` text nullable
- `status` text not null default `open`
  - examples: `open`, `in_progress`, `blocked`, `resolved`, `dismissed`
- `priority` text not null default `medium`
  - examples: `low`, `medium`, `high`, `critical`
- `severity` text nullable
- `due_at` timestamptz/timestamp nullable
- `metadata_json` json/jsonb nullable
- `created_by_user_id` int nullable FK
- `resolved_by_user_id` int nullable FK
- `resolved_at` timestamp nullable
- `created_at` timestamp not null
- `updated_at` timestamp not null

Indexes:

- `(status, priority, due_at)`
- `(system_id, status)`
- `(buyer_user_id, status)`
- `(po_number)`
- `(reference_type, reference_number)`

### 2. `purchasing_assignments`

Purpose:

- app-owned branch or workload ownership
- does not alter ERP buyer assignment

Columns:

- `id` bigint/integer PK
- `assignment_type` text not null
  - `branch`, `supplier`, `queue_override`
- `system_id` text not null
- `buyer_user_id` int nullable FK `app_users.id`
- `assigned_by_user_id` int nullable FK `app_users.id`
- `supplier_key` text nullable
- `item_ptr` text nullable
- `active` bool not null default true
- `notes` text nullable
- `created_at` timestamp not null
- `updated_at` timestamp not null

Indexes:

- `(system_id, active)`
- `(buyer_user_id, active)`
- `(assignment_type, system_id)`

### 3. `purchasing_notes`

Purpose:

- threaded internal collaboration against PO or exception context

Columns:

- `id` bigint/integer PK
- `entity_type` text not null
  - `po`, `queue_item`, `exception`, `supplier`
- `entity_id` text not null
- `po_number` text nullable
- `system_id` text nullable
- `body` text not null
- `is_internal` bool not null default true
- `created_by_user_id` int nullable FK `app_users.id`
- `created_at` timestamp not null

Indexes:

- `(entity_type, entity_id)`
- `(po_number, created_at desc)`
- `(system_id, created_at desc)`

### 4. `purchasing_tasks`

Purpose:

- due-dated follow-up actions

Columns:

- `id` bigint/integer PK
- `title` text not null
- `description` text nullable
- `po_number` text nullable
- `queue_item_id` int nullable FK `purchasing_work_queue.id`
- `system_id` text nullable
- `assignee_user_id` int nullable FK `app_users.id`
- `created_by_user_id` int nullable FK `app_users.id`
- `status` text not null default `open`
- `priority` text not null default `medium`
- `due_at` timestamp nullable
- `completed_at` timestamp nullable
- `created_at` timestamp not null
- `updated_at` timestamp not null

Indexes:

- `(assignee_user_id, status, due_at)`
- `(system_id, status, due_at)`
- `(po_number)`
- `(queue_item_id)`

### 5. `purchasing_approvals`

Purpose:

- app-side gating for internal approvals
- not ERP write-back approval state

Columns:

- `id` bigint/integer PK
- `approval_type` text not null
  - `high_dollar`, `urgent_buy`, `off_contract`, `receiving_variance`
- `entity_type` text not null
- `entity_id` text not null
- `po_number` text nullable
- `system_id` text nullable
- `requested_by_user_id` int nullable FK
- `approver_user_id` int nullable FK
- `status` text not null default `pending`
  - `pending`, `approved`, `rejected`, `withdrawn`
- `reason` text nullable
- `decision_notes` text nullable
- `requested_at` timestamp not null
- `decided_at` timestamp nullable

Indexes:

- `(status, requested_at desc)`
- `(system_id, status)`
- `(po_number)`
- `(entity_type, entity_id)`

### 6. `purchasing_exception_events`

Purpose:

- app-owned representation of purchasing/receiving exceptions

Columns:

- `id` bigint/integer PK
- `event_type` text not null
  - `receiving_variance`, `po_overdue`, `partial_after_expected`, `reopen_required`, `cost_packet_followup`, `checkin_review_required`
- `event_status` text not null default `open`
  - `open`, `acknowledged`, `resolved`, `dismissed`
- `po_number` text nullable
- `receiving_number` text nullable
- `queue_item_id` int nullable FK `purchasing_work_queue.id`
- `system_id` text nullable
- `supplier_key` text nullable
- `severity` text not null default `medium`
- `summary` text not null
- `details` text nullable
- `metadata_json` json/jsonb nullable
- `created_by_user_id` int nullable FK
- `resolved_by_user_id` int nullable FK
- `created_at` timestamp not null
- `resolved_at` timestamp nullable

Indexes:

- `(event_status, severity, created_at desc)`
- `(system_id, event_status)`
- `(po_number)`
- `(receiving_number)`
- `(queue_item_id)`

### 7. `purchasing_dashboard_snapshots`

Purpose:

- optional cache rows for dashboard performance
- safe to delete/rebuild

Columns:

- `id` bigint/integer PK
- `snapshot_type` text not null
  - `manager`, `buyer`
- `system_id` text nullable
- `buyer_user_id` int nullable FK
- `payload` json/jsonb not null
- `captured_at` timestamp not null

Indexes:

- `(snapshot_type, captured_at desc)`
- `(system_id, snapshot_type, captured_at desc)`
- `(buyer_user_id, snapshot_type, captured_at desc)`

### 8. `purchasing_activity_log`

Purpose:

- app-owned audit log for state changes and collaboration events

Columns:

- `id` bigint/integer PK
- `activity_type` text not null
  - `note_created`, `task_created`, `task_completed`, `approval_requested`, `approval_updated`, `queue_resolved`, `submission_linked`
- `entity_type` text not null
- `entity_id` text not null
- `po_number` text nullable
- `system_id` text nullable
- `actor_user_id` int nullable FK
- `summary` text not null
- `before_state` json/jsonb nullable
- `after_state` json/jsonb nullable
- `details` json/jsonb nullable
- `created_at` timestamp not null

Indexes:

- `(entity_type, entity_id, created_at desc)`
- `(po_number, created_at desc)`
- `(system_id, created_at desc)`
- `(actor_user_id, created_at desc)`

## `po_submissions` Compatibility Extension

Do not replace `po_submissions`.

Extend it so warehouse photo check-ins remain part of the larger purchasing workflow.

Recommended additions:

- `submission_type` text not null default `receiving_checkin`
- `priority` text nullable
- `queue_item_id` int nullable FK `purchasing_work_queue.id`

Keep existing semantics:

- warehouse can submit photos / notes
- buyers and manager can review those submissions in the purchasing workflow

Phase 1 use:

- treat a new `po_submissions` row as a queue/event signal
- optionally generate a matching `purchasing_work_queue` row when a submission is created

## Updated API Contract Assumptions

All branch scoping in Phase 1 should be `system_id`-driven.

### Manager dashboard API

Source now:

- `app_po_search`
- `app_po_header`
- `app_po_receiving_summary`
- app-owned workflow tables
- `po_submissions`

Do not require:

- `app_supplier_performance`
- `app_branch_inventory_buy_signals`
- PPO mirrors

Degraded Phase 1 behavior:

- supplier watchlist is computed from overdue open POs, not true supplier scorecards
- branch transfer opportunities show `0` or “not available yet”
- suggested buy KPIs show `0` until PPO mirrors go live

### Buyer queue API

Source now:

- app-owned `purchasing_work_queue`
- derived queue items from:
  - overdue POs in `app_po_search`
  - pending receiving evidence in `po_submissions`

Do not require PPO mirrors yet.

### PO workspace API

Source now:

- `app_po_header`
- `app_po_detail`
- `app_po_receiving_summary`
- `po_submissions`
- app-owned notes/tasks/approvals/exceptions/activity

Degraded Phase 1 behavior:

- supplier location/contact cards may be incomplete until supplier mirrors go live
- cost packet details should show placeholder copy unless purchase-cost mirrors are available
- receiving lifecycle details are inferred from current receiving rows and app exceptions, not `receiving_status`

### Suggested-buy API

Phase 1 source:

- if `erp_mirror_ppo_header` and `erp_mirror_ppo_detail` are live, use them
- otherwise return an empty set with “Suggested buy data not available yet”

Degraded Phase 1 behavior:

- page exists
- counts are safe
- no fake suggested-buy data should be manufactured from PO history

## Required Changes To Existing PO Views / Materialized Views

### `app_po_header` materialized view

Keep using it, but confirm it exposes at least:

- `po_number`
- `system_id`
- `supplier_name`
- `supplier_code`
- `po_status`
- `order_date`
- `expect_date`
- `total_amount` and/or `open_amount`

Recommended next improvement:

- ensure `system_id` is indexed in the MV or underlying unique/indexed source for branch-scoped filtering

Because it is materialized:

- define refresh cadence clearly
- if UI has a manual refresh action, use `REFRESH MATERIALIZED VIEW CONCURRENTLY` only if the MV is already indexed correctly for concurrent refresh

### `app_po_search` view

Make sure it is explicitly branch-safe around `system_id`.

Recommended contract:

- `po_number`
- `supplier_name`
- `supplier_code`
- `system_id`
- `order_date`
- `expect_date`
- `po_status`
- `receipt_count`

Do not require `branch_code`.

### `app_po_detail` view

Confirm it uses the current live mirrors:

- `erp_mirror_po_detail`
- optionally `erp_mirror_item`

No dependency should be introduced on:

- `erp_mirror_item_supplier`
- `erp_mirror_supplier_dim`

until they are live.

### `app_po_receiving_summary` view

Confirm it only depends on currently live receiving mirrors:

- `erp_mirror_receiving_header`
- `erp_mirror_receiving_detail`

Do not require `erp_mirror_receiving_status` yet.

When `receiving_status` arrives later, extend the view rather than replacing its contract.

## Phase 1 Plan That Works With Live DB First

### Phase 1A: Safe live-DB launch

Implement:

- manager dashboard from `app_po_header` and `app_po_search`
- buyer queue from app tables plus derived overdue/check-in items
- PO workspace from current PO views + `po_submissions`
- app-owned notes/tasks/approvals/exceptions/activity tables
- branch scoping entirely from `system_id`

Degraded behaviors accepted in 1A:

- no true suggested-buy workflow unless PPO mirrors are connected
- no supplier scorecards
- no item-supplier recommendation logic
- no supplier geo cards beyond whatever already exists in current views

### Phase 1B: Turn on PPO-backed suggested buys

When live:

- `erp_mirror_ppo_header`
- `erp_mirror_ppo_detail`

Add:

- suggested-buy dashboard counts
- buyer review workspace for saved PPO batches
- queue generation for PPO review tasks

### Phase 1C: Add supplier and item-supplier enrichment

When live:

- `erp_mirror_item_supplier`
- `erp_mirror_supplier_dim`
- `erp_mirror_suppname`
- `erp_mirror_supp_ship_from`

Add:

- supplier watchlist with better grouping and contact info
- supplier city/state cards
- item-supplier fallback / preferred source context
- improved assignment rules by supplier

### Phase 1D: Add policy and receiving-state enrichment

When live:

- `erp_mirror_purchase_type`
- `erp_mirror_purchase_costs`
- `erp_mirror_param_po`
- `erp_mirror_param_po_cost`
- `erp_mirror_receiving_status`

Add:

- richer purchase-type labeling
- cost packet workflows
- finalize/recalc policy labels
- better receiving-state visualization

## Migration And Compatibility Notes

### Safe app migration boundaries

The Flask app should migrate only:

- app-owned purchasing workflow tables
- `po_submissions` extensions

It should **not** attempt to create or own:

- ERP mirror tables
- Supabase-managed read-model views/materialized views

Those remain managed by the mirror/sync side and database-side SQL deployment process.

### Column naming compatibility

For app-owned tables:

- use `system_id` for branch scoping instead of `branch_code` in new purchasing tables if you want strict alignment with live purchasing source shape

If existing app conventions favor `branch_code`, it is still safe to:

- store the actual `system_id` value in that field
- document that “branch_code” in app-owned purchasing tables is the ERP `system_id`

Preferred direction for new purchasing work is:

- use `system_id` in new tables and APIs
- alias to UI label “Branch”

### View compatibility

Because `app_po_header` is materialized:

- rollout must ensure refresh behavior is known
- API code should tolerate stale-but-valid rows
- do not couple user writes to immediate MV visibility

### Empty or low-row-count mirrors

Known live counts:

- `ppo_header`: 9
- `ppo_detail`: 86
- `param_po`: 0
- `receiving_status`: 0

Implications:

- suggested-buy UI should be feature-flagged or explicitly “limited preview” at first
- `param_po` should be treated as missing, not broken
- `receiving_status` should not drive any required Phase 1 logic

## Temporary Degraded UI/API Behavior

These are intentional until more mirrors arrive:

- Suggested buys:
  - show empty state if PPO mirrors are unavailable or sparse
  - do not fake counts from unrelated data

- Supplier watchlist:
  - derive from overdue POs and receiving exceptions only
  - do not show OTIF/lead variance scorecards yet

- Supplier details:
  - show only what current PO views expose
  - defer city/state/contact enrichments until supplier mirrors are live

- Branch transfer opportunities:
  - not available in Phase 1A

- Receiving state:
  - infer from receiving rows and app events
  - do not show full lifecycle badges that imply `receiving_status` is already connected

## Recommended Immediate Next Step

Connect the Phase 1 purchasing module only to:

- `app_po_header`
- `app_po_search`
- `app_po_detail`
- `app_po_receiving_summary`
- `po_submissions`
- app-owned workflow tables

Then add PPO and supplier enrichment as incremental layers without changing the app-owned workflow contract.

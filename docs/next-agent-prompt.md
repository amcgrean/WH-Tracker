# Next Agent Prompt: Post-Overhaul — Remaining Items

## Context
The full 8-phase UI/UX overhaul (Phases 0-7) is **COMPLETE** as of 2026-03-27 (commit `94ba468` on `main-fly`). The full spec was in `docs/phase 1 audit.md`. All templates now use the glassmorphic design system, inline styles have been extracted to `style.css`, and a PWA shell is in place.

**Read the memory files first** — they contain architecture decisions, known pitfalls, and the full phase completion record. Especially read `project_ui_overhaul_status.md` and `project_branch_architecture.md`.

## What's Done (DO NOT redo)
Everything in Phases 0-7 is complete. See `docs/NEXT_AGENT_HANDOFF_2026-03-27.md` for the full list.

## What Remains

### 1. PWA Icons (quick task)
Create or source two PNG icons and place in `app/static/icons/`:
- `icon-192.png` (192x192) — Beisser "B" or cubes logo on green `#004526` background
- `icon-512.png` (512x512) — Same design, larger
These are referenced by `app/static/manifest.json`.

### 2. Kiosk/TV Branch-Aware Data Filtering (medium task)
Routes and templates exist under `app/templates/kiosk/` and `app/templates/tv/`, but data queries show ALL data with a notice badge. The kiosk/TV URL path contains the branch (e.g., `/kiosk/20GR/pickers`), but the underlying queries in `routes.py` don't filter by it yet.

**Key constraint:** Pick data (Pickster, Pick, PickAssignment) has NO `branch_code` field. WorkOrder has `branch_code` and CAN be filtered. For pick-related kiosk/TV views, you can only filter if you join through WorkOrder → Pick or through ERP mirror data.

### 3. Production Cutover (when user is ready)
- Merge `main-fly` → `main`
- Verify Fly deployment picks up the changes
- Resolve UPLOAD_FOLDER local storage issue (Fly Volume or object storage)

### 4. Pick Module Branch Migration (future — DB migration required)
- Add `branch_code` to Pickster, Pick, PickAssignment, WorkOrderAssignment
- DB migration, admin UI, update queries
- This enables true branch filtering in kiosk/TV views

### 5. Schema Drift Cleanup (optional)
- ALTER COLUMN `erp_mirror_so_detail.so_id` and `erp_mirror_cust_shipto.seq_num` to varchar
- Currently handled via CAST in `app/Services/erp_service.py`

## Architecture Rules (still apply)
1. **No DB migrations** unless specifically for item #4 above
2. **Don't fake branch isolation** where data doesn't support it
3. **Preserve backward compatibility**
4. **Branch filter pattern:** backend reads `request.args.get('branch') or session.get('selected_branch')`, normalizes with `normalize_branch()` from `branch_utils`
5. All templates extending `base.html` automatically get the sidebar branch selector + PWA

## Known Pitfalls
1. **Edit tool requires Read first** — always Read files before editing
2. **Merge conflicts on push** — `app/__init__.py` and `app/templates/base.html` are hot files. Fetch and rebase before pushing.
3. **fly.toml has unstaged changes** — don't accidentally stage it
4. Use CSS custom properties from `:root` in `style.css` instead of hardcoding values

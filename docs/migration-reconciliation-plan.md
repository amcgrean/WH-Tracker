# Alembic Migration Reconciliation Plan

**Status:** PHASE M1 complete — analysis only, no migration files changed yet.

---

## 1. Migration Graph (as of 2026-03-26)

```
3e6c5d3f8ce5  initial
    ↓
2b3fda096311  add_user_type_to_pickster
    ↓
83fabbe397a1  add_pickassignment_table
    ↓
a1c4e2f9b803  add_credit_images_table
    ├──────────────────────────────────────┐
    ↓                                      ↓
c9d8e7f6a5b4  add_audit_trail     f3a8b9c4d5e6  add_normalized_erp_mirror_tables
    ↓                                      │
d1e2f3a4b5c6  add_customer_notes_table     │
    ↓                                      ↓
    └────────► b4c5d6e7f8a9  merge ◄───────┘       ← existing merge migration
                   ├─────────────────────────────────────────┐
                   ↓                                         ↓
           e1f2a3b4c5d6  add_sales_perf_indexes    a2b3c4d5e6f7  add_wo_assignments
                   ↓                                   (HEAD #2)
           f9a1b2c3d4e5  add_mirror_perf_indexes_v2
                   ↓
           a7b8c9d0e1f2  add_trgm_search_indexes
               (HEAD #1)

f3a8b9c4d5e6  ──► a8f3c2d1e9b7  add_gps_coords_to_cust_shipto
                      (HEAD #3)   ← incorrectly parented to f3a8b9c4d5e6
```

### Three current heads

| Head | Revision | Description |
|------|----------|-------------|
| #1 | `a7b8c9d0e1f2` | End of main perf-index chain (trgm indexes) |
| #2 | `a2b3c4d5e6f7` | `wo_assignments` table — branches from `b4c5d6e7f8a9` instead of `a7b8c9d0e1f2` |
| #3 | `a8f3c2d1e9b7` | GPS coords — branches from `f3a8b9c4d5e6` (before the existing merge!) |

---

## 2. Contents of the Failing Migration

**File:** `migrations/versions/a8f3c2d1e9b7_add_gps_coords_to_cust_shipto.py`

`upgrade()` calls:
- `op.add_column('erp_mirror_cust_shipto', Column('lat', Numeric(9,6)))`
- `op.add_column('erp_mirror_cust_shipto', Column('lon', Numeric(9,6)))`
- `op.add_column('erp_mirror_cust_shipto', Column('geocoded_at', DateTime))`
- `op.add_column('erp_mirror_cust_shipto', Column('geocode_source', String(64)))`
- `op.create_index('ix_erp_mirror_cust_shipto_geocoded', ...['geocoded_at'])`

The error at runtime: `column "lat" already exists` — the Fly DB already has these columns
but Alembic never recorded this revision as applied (it failed mid-upgrade and was never stamped).

---

## 3. Root Cause

**Two independent authoring mistakes created three heads:**

### Problem A — GPS migration parented to wrong revision (HEAD #3)
`a8f3c2d1e9b7` was authored 2026-03-21, **after** the merge migration `b4c5d6e7f8a9`
(dated 2026-03-19) had already subsumed `f3a8b9c4d5e6` into the main line.
The author set `down_revision = 'f3a8b9c4d5e6'` (a node that was already folded
into a merge), causing it to create a new branch that diverges *before* the merge.
It should have been `down_revision = 'b4c5d6e7f8a9'` (or later).

### Problem B — WO assignments migration parented to a non-tip node (HEAD #2)
`a2b3c4d5e6f7` was authored 2026-03-25 with `down_revision = 'b4c5d6e7f8a9'`,
but the tip of the main chain at that point was already `a7b8c9d0e1f2`.
This creates a second branch off an intermediate node.

### Problem C — GPS columns already present in Fly DB
The four GPS columns (`lat`, `lon`, `geocoded_at`, `geocode_source`) are defined in
`app/Models/models.py` and are actively used by `sync_erp.py` and `erp_service.py`.
They must have been added to the Fly database by some means other than a tracked Alembic run
(possibly: a prior migration attempt, a manual `ALTER TABLE`, or a partial schema creation).
Because `a8f3c2d1e9b7` never successfully completed, the revision was never recorded in
`alembic_version`, so Alembic sees it as unapplied and tries to run it again — then
hits the duplicate-column error.

---

## 4. Recommended Safest Fix Path (for PHASE M2)

### Step 1 — Make `a8f3c2d1e9b7` idempotent
Since this migration has **never been successfully recorded** in `alembic_version` (it
always fails), it is safe to edit it in-place. Replace the four `op.add_column` calls
and the `op.create_index` call with raw-SQL equivalents that use PostgreSQL's
`IF NOT EXISTS` semantics. This allows the migration to succeed regardless of whether
the columns already exist, which unblocks the `flask db upgrade heads` step.

This is safe because:
- The migration has never been stamped as applied on any DB.
- No downstream migration depends on specific behavior of this upgrade step.
- Fresh DBs will get the columns added normally.
- DBs that already have the columns will silently skip the add.

### Step 2 — Create a merge migration for all three heads
After `a8f3c2d1e9b7` is idempotent, create a single merge migration:

```
down_revision = ('a7b8c9d0e1f2', 'a2b3c4d5e6f7', 'a8f3c2d1e9b7')
```

This produces one clean head and unblocks plain `flask db upgrade`.

### What NOT to do
- Do **not** re-parent `a8f3c2d1e9b7` by changing its `down_revision` — that would
  invalidate the revision ID chain for any DB that was partially upgraded.
- Do **not** delete `a8f3c2d1e9b7` — the GPS columns are actively used and must be
  present for a fresh DB to have them after a clean `flask db upgrade`.
- Do **not** stamp `a8f3c2d1e9b7` as applied on the live DB without making it
  idempotent first — a future fresh DB would then fail.

---

## 5. Files Inspected

| File | Purpose |
|------|---------|
| `migrations/versions/3e6c5d3f8ce5_initial_migration.py` | Root of graph |
| `migrations/versions/2b3fda096311_add_user_type_to_pickster.py` | Chain node |
| `migrations/versions/83fabbe397a1_add_pickassignment_table.py` | Chain node |
| `migrations/versions/a1c4e2f9b803_add_credit_images_table.py` | Branching node |
| `migrations/versions/f3a8b9c4d5e6_add_normalized_erp_mirror_tables.py` | Branch root + GPS parent |
| `migrations/versions/c9d8e7f6a5b4_add_audit_trail.py` | Other branch |
| `migrations/versions/d1e2f3a4b5c6_add_customer_notes_table.py` | Chain node |
| `migrations/versions/b4c5d6e7f8a9_merge_customer_notes_and_mirror_heads.py` | Existing merge |
| `migrations/versions/e1f2a3b4c5d6_add_sales_perf_indexes.py` | Chain node post-merge |
| `migrations/versions/f9a1b2c3d4e5_add_mirror_perf_indexes_v2.py` | Chain node |
| `migrations/versions/a7b8c9d0e1f2_add_trgm_search_indexes.py` | **HEAD #1** |
| `migrations/versions/a2b3c4d5e6f7_add_wo_assignments_table.py` | **HEAD #2** |
| `migrations/versions/a8f3c2d1e9b7_add_gps_coords_to_cust_shipto.py` | **HEAD #3** (failing) |
| `app/Models/models.py` | Confirms GPS columns are in ORM model |
| `sync_erp.py` | Confirms GPS columns are actively queried |
| `app/Services/erp_service.py` | Confirms GPS columns are used in queries |

---

## 6. PHASE M2 Decision

**Action:** Edit `a8f3c2d1e9b7` to make its `upgrade()` idempotent using raw SQL,
then create a new merge migration for all three heads.

**This is preferable to** creating a wholly new corrective migration because:
- `a8f3c2d1e9b7` has never been applied (no alembic_version row for it exists).
- Editing a never-applied migration is equivalent to correcting it before first use.
- Creating a new migration would leave `a8f3c2d1e9b7` as a permanently broken dead
  branch in the graph, which is confusing and misleading.

---

---

## PHASE M2 — Implemented Fix (2026-03-26)

### Changes made

#### 1. `migrations/versions/a8f3c2d1e9b7_add_gps_coords_to_cust_shipto.py` — made idempotent

The four `op.add_column` calls and `op.create_index` call were replaced with raw
PostgreSQL SQL using `ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.

The `downgrade()` was left unchanged — it uses standard `op.drop_column` /
`op.drop_index`, which is correct for a rollback (if you're rolling back, the
columns should be removed).

**Why this is safe:** This migration has never been successfully recorded in
`alembic_version` on any database. Editing a never-applied migration is equivalent
to correcting it before first use. Fresh databases get the columns added normally;
databases that already have the columns (including Supabase) skip the add silently.

#### 2. `migrations/versions/c1d2e3f4a5b6_merge_three_heads.py` — new merge migration

```
down_revision = ('a7b8c9d0e1f2', 'a2b3c4d5e6f7', 'a8f3c2d1e9b7')
```

Empty `upgrade()` and `downgrade()`. This migration's only purpose is to give
Alembic a single head so `flask db upgrade` works without additional flags.

### Resulting graph (after M2)

```
... → b4c5d6e7f8a9 (existing merge)
          ├──► e1f2a3b4c5d6 → f9a1b2c3d4e5 → a7b8c9d0e1f2 ─────┐
          └──► a2b3c4d5e6f7 ────────────────────────────────────┤
                                                                  ├──► c1d2e3f4a5b6  (new HEAD, single)
f3a8b9c4d5e6 → a8f3c2d1e9b7 (idempotent GPS) ───────────────────┘
```

### What existing DBs need after redeploy

See PHASE M3 section (to be added) for exact Fly recovery commands.

Short answer for a DB that has the GPS columns but has never had `a8f3c2d1e9b7` stamped:

```bash
flask db upgrade
```

This will:
1. Apply `a8f3c2d1e9b7` (idempotent — no-op on columns that already exist)
2. Apply `a2b3c4d5e6f7` (creates `wo_assignments` table — real schema change)
3. Apply `c1d2e3f4a5b6` (empty merge migration — just writes alembic_version row)

Result: one head, clean state.

*PHASE M2 completed: 2026-03-26*

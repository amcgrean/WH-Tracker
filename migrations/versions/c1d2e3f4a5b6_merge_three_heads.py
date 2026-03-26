"""Merge three divergent heads into a single clean tip

Revision ID: c1d2e3f4a5b6
Revises: a7b8c9d0e1f2, a2b3c4d5e6f7, a8f3c2d1e9b7
Create Date: 2026-03-26 01:53:13.000000

Background
----------
Three heads existed due to two authoring mistakes:

  HEAD #1  a7b8c9d0e1f2  add_trgm_search_indexes
           (correct tip of the main perf-index chain)

  HEAD #2  a2b3c4d5e6f7  add_wo_assignments_table
           (should have parented to a7b8c9d0e1f2; was accidentally parented
           to b4c5d6e7f8a9, creating a second branch off an intermediate node)

  HEAD #3  a8f3c2d1e9b7  add_gps_coords_to_cust_shipto
           (should have parented to b4c5d6e7f8a9 or later; was accidentally
           parented to f3a8b9c4d5e6 — a node already subsumed by the earlier
           merge migration b4c5d6e7f8a9 — creating a branch before the merge)

a8f3c2d1e9b7 was also made idempotent (ADD COLUMN IF NOT EXISTS) because the
GPS columns already existed in the Supabase DB from a prior partial run before
Alembic could record the revision.

This merge migration has no schema effect; it only establishes a single head
so that plain `flask db upgrade` works without --branch or explicit targets.
"""

revision = 'c1d2e3f4a5b6'
down_revision = ('a7b8c9d0e1f2', 'a2b3c4d5e6f7', 'a8f3c2d1e9b7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

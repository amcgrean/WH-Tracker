"""Merge order_writer and branch_code migration heads

The sales hub refactor (d2e3f4a5b6c7) and branch_code addition
(j4k5l6m7n8o9) created two independent heads.  This merge migration
establishes a single head so that `flask db upgrade` works.

Revision ID: k5l6m7n8o9p0
Revises: d2e3f4a5b6c7, j4k5l6m7n8o9
Create Date: 2026-03-28 12:00:00.000000

"""

revision = 'k5l6m7n8o9p0'
down_revision = ('d2e3f4a5b6c7', 'j4k5l6m7n8o9')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

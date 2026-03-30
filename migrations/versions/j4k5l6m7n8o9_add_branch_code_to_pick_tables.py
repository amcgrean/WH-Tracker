"""Add branch_code to pick, pick_assignments, pickster, wo_assignments

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-03-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j4k5l6m7n8o9'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL with IF NOT EXISTS guards — columns/indexes may already exist
    # if they were applied outside of Alembic.
    op.execute("ALTER TABLE pick ADD COLUMN IF NOT EXISTS branch_code VARCHAR(32)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_branch_code ON pick (branch_code)")

    op.execute("ALTER TABLE pick_assignments ADD COLUMN IF NOT EXISTS branch_code VARCHAR(32)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_assignments_branch_code ON pick_assignments (branch_code)")

    op.execute("ALTER TABLE pickster ADD COLUMN IF NOT EXISTS branch_code VARCHAR(32)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pickster_branch_code ON pickster (branch_code)")

    op.execute("ALTER TABLE wo_assignments ADD COLUMN IF NOT EXISTS branch_code VARCHAR(32)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wo_assignments_branch_code ON wo_assignments (branch_code)")


def downgrade():
    op.drop_index('ix_wo_assignments_branch_code', 'wo_assignments')
    op.drop_column('wo_assignments', 'branch_code')

    op.drop_index('ix_pickster_branch_code', 'pickster')
    op.drop_column('pickster', 'branch_code')

    op.drop_index('ix_pick_assignments_branch_code', 'pick_assignments')
    op.drop_column('pick_assignments', 'branch_code')

    op.drop_index('ix_pick_branch_code', 'pick')
    op.drop_column('pick', 'branch_code')

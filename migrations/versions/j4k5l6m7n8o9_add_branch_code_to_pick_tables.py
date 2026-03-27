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
    op.add_column('pick', sa.Column('branch_code', sa.String(32), nullable=True))
    op.create_index('ix_pick_branch_code', 'pick', ['branch_code'])

    op.add_column('pick_assignments', sa.Column('branch_code', sa.String(32), nullable=True))
    op.create_index('ix_pick_assignments_branch_code', 'pick_assignments', ['branch_code'])

    op.add_column('pickster', sa.Column('branch_code', sa.String(32), nullable=True))
    op.create_index('ix_pickster_branch_code', 'pickster', ['branch_code'])

    op.add_column('wo_assignments', sa.Column('branch_code', sa.String(32), nullable=True))
    op.create_index('ix_wo_assignments_branch_code', 'wo_assignments', ['branch_code'])


def downgrade():
    op.drop_index('ix_wo_assignments_branch_code', 'wo_assignments')
    op.drop_column('wo_assignments', 'branch_code')

    op.drop_index('ix_pickster_branch_code', 'pickster')
    op.drop_column('pickster', 'branch_code')

    op.drop_index('ix_pick_assignments_branch_code', 'pick_assignments')
    op.drop_column('pick_assignments', 'branch_code')

    op.drop_index('ix_pick_branch_code', 'pick')
    op.drop_column('pick', 'branch_code')

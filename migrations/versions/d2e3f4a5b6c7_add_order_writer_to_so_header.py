"""Add order_writer column to erp_mirror_so_header

Maps to Agility sales_agent_3 (the rep who wrote up the order).
salesperson (existing) maps to sales_agent_1 (account rep).

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('erp_mirror_so_header', schema=None) as batch_op:
        batch_op.add_column(sa.Column('order_writer', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('erp_mirror_so_header', schema=None) as batch_op:
        batch_op.drop_column('order_writer')

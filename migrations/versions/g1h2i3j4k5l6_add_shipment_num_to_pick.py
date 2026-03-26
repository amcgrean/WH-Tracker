"""Add shipment_num column to pick table

Revision ID: g1h2i3j4k5l6
Revises: f9a1b2c3d4e5
Create Date: 2026-03-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g1h2i3j4k5l6'
down_revision = 'f9a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pick', sa.Column('shipment_num', sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column('pick', 'shipment_num')

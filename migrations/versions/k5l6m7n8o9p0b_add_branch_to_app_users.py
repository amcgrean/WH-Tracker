"""Add branch column to app_users

Revision ID: k5l6m7n8o9p0b
Revises: k5l6m7n8o9p0
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k5l6m7n8o9p0b'
down_revision = 'k5l6m7n8o9p0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS branch VARCHAR(16)")


def downgrade():
    op.drop_column('app_users', 'branch')

"""Add dashboard_stats table for pre-computed dashboard counts

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'n8o9p0q1r2s3'
down_revision = 'm7n8o9p0q1r2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboard_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('open_picks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('handling_breakdown_json', sa.Text(), nullable=True),
        sa.Column('open_work_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Seed the single row so UPSERTs work immediately
    op.execute("INSERT INTO dashboard_stats (id, open_picks, open_work_orders) VALUES (1, 0, 0)")


def downgrade():
    op.drop_table('dashboard_stats')

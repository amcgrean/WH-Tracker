"""Migrate dashboard_stats to per-branch schema (system_id TEXT primary key)

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'o9p0q1r2s3t4'
down_revision = 'n8o9p0q1r2s3'
branch_labels = None
depends_on = None


def upgrade():
    # If dashboard_stats was pre-created with the final per-branch schema
    # (system_id TEXT PRIMARY KEY) skip the drop/recreate to avoid data loss.
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dashboard_stats' AND column_name = 'system_id'"
        )
    ).fetchone()
    if row:
        return  # Already in the correct per-branch shape.

    op.drop_table('dashboard_stats')
    op.create_table(
        'dashboard_stats',
        sa.Column('system_id', sa.String(32), primary_key=True),
        sa.Column('open_picks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('handling_breakdown_json', sa.Text(), nullable=True),
        sa.Column('open_work_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('dashboard_stats')
    op.create_table(
        'dashboard_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('open_picks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('handling_breakdown_json', sa.Text(), nullable=True),
        sa.Column('open_work_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute("INSERT INTO dashboard_stats (id, open_picks, open_work_orders) VALUES (1, 0, 0)")

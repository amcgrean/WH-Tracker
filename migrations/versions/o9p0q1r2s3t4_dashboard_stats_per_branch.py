"""Migrate dashboard_stats to per-branch schema (system_id TEXT primary key)

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision = 'o9p0q1r2s3t4'
down_revision = 'n8o9p0q1r2s3'
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        return {column["name"] for column in inspector.get_columns(table_name)}
    except Exception:
        return set()


def upgrade():
    # If dashboard_stats was pre-created with the final per-branch schema
    # (system_id TEXT PRIMARY KEY) skip the drop/recreate to avoid data loss.
    if not _table_exists('dashboard_stats'):
        op.create_table(
            'dashboard_stats',
            sa.Column('system_id', sa.String(32), primary_key=True),
            sa.Column('open_picks', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('handling_breakdown_json', sa.Text(), nullable=True),
            sa.Column('open_work_orders', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        return

    columns = _table_columns('dashboard_stats')
    if 'system_id' in columns:
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
    if _table_exists('dashboard_stats'):
        op.drop_table('dashboard_stats')
    op.create_table(
        'dashboard_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('open_picks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('handling_breakdown_json', sa.Text(), nullable=True),
        sa.Column('open_work_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute(text("INSERT INTO dashboard_stats (id, open_picks, open_work_orders) VALUES (1, 0, 0) ON CONFLICT DO NOTHING"))

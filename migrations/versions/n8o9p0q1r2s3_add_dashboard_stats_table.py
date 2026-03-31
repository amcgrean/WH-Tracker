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
    # dashboard_stats may have been pre-created directly in Supabase (with either
    # the legacy id-PK schema or the final system_id-PK schema from o9p0q1r2s3t4).
    # Use IF NOT EXISTS so this migration is safe to run against a DB that already
    # has the table in any form.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_stats (
            id INTEGER PRIMARY KEY,
            open_picks INTEGER NOT NULL DEFAULT 0,
            handling_breakdown_json TEXT,
            open_work_orders INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "INSERT INTO dashboard_stats (id, open_picks, open_work_orders) "
        "VALUES (1, 0, 0) ON CONFLICT DO NOTHING"
    )


def downgrade():
    op.drop_table('dashboard_stats')

"""add estimating_user_id to app_users

Links a WH-Tracker AppUser to a legacy beisser-takeoff user record so that
existing estimator accounts can be mapped during the cutover from Neon to
Supabase.  No FK constraint is added — this is a cross-schema (and currently
cross-database) reference that will be resolved in application code.

Supported roles for the "estimator" entry-point:
  Existing roles in app_users.roles (JSON array):
    admin, ops, sales, picker, supervisor, purchasing, manager,
    warehouse, production, delivery, dispatch, credits
  Added by this migration (documentation only — stored as plain JSON strings):
    estimator   — can access beisser-takeoff bid management features
    designer    — can access design/drawing tools within beisser-takeoff

Revision ID: t3u4v5w6x7y8
Revises: s2t3u4v5w6x7
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 't3u4v5w6x7y8'
down_revision = 's2t3u4v5w6x7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'app_users',
        sa.Column('estimating_user_id', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('app_users', 'estimating_user_id')

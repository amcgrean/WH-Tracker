"""Backfill schema skipped by overlapping migration heads (ERP sync chain fix)

When migrations a1c4e2f9b803 (credit_images) and c9d8e7f6a5b4 (audit trail /
completed_by_id) were inserted mid-chain AFTER d1e2f3a4b5c6 had already been
applied to production, the DB ended up with both 83fabbe397a1 and d1e2f3a4b5c6
in alembic_version but was missing the schema from the two inserted migrations.

This migration idempotently applies all those missing changes.

Revision ID: f3a4b5c6d7e8
Revises: d1e2f3a4b5c6
Create Date: 2026-03-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # --- from a1c4e2f9b803: credit_images table ---
    if 'credit_images' not in existing_tables:
        op.create_table(
            'credit_images',
            sa.Column('id',            sa.Integer(),     nullable=False),
            sa.Column('rma_number',    sa.String(20),    nullable=False),
            sa.Column('filename',      sa.String(256),   nullable=False),
            sa.Column('filepath',      sa.String(512),   nullable=False),
            sa.Column('email_from',    sa.String(256),   nullable=True),
            sa.Column('email_subject', sa.String(512),   nullable=True),
            sa.Column('received_at',   sa.DateTime(),    nullable=True),
            sa.Column('uploaded_at',   sa.DateTime(),    nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_credit_images_rma_number', 'credit_images', ['rma_number'])

    # --- from c9d8e7f6a5b4: notes on pick ---
    pick_cols = {c['name'] for c in inspector.get_columns('pick')}
    if 'notes' not in pick_cols:
        op.add_column('pick', sa.Column('notes', sa.Text(), nullable=True))

    # --- from c9d8e7f6a5b4: notes and completed_by_id on work_orders ---
    wo_cols = {c['name'] for c in inspector.get_columns('work_orders')}
    if 'notes' not in wo_cols:
        op.add_column('work_orders', sa.Column('notes', sa.Text(), nullable=True))
    if 'completed_by_id' not in wo_cols:
        op.add_column('work_orders', sa.Column('completed_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_work_orders_completed_by_id',
            'work_orders', 'pickster',
            ['completed_by_id'], ['id']
        )

    # --- from c9d8e7f6a5b4: audit_events table ---
    if 'audit_events' not in existing_tables:
        op.create_table(
            'audit_events',
            sa.Column('id',          sa.Integer(),     nullable=False),
            sa.Column('event_type',  sa.String(50),    nullable=False),
            sa.Column('entity_type', sa.String(50),    nullable=False),
            sa.Column('entity_id',   sa.Integer(),     nullable=True),
            sa.Column('so_number',   sa.String(128),   nullable=True),
            sa.Column('actor_id',    sa.Integer(),     nullable=True),
            sa.Column('notes',       sa.Text(),        nullable=True),
            sa.Column('occurred_at', sa.DateTime(),    nullable=False),
            sa.ForeignKeyConstraint(['actor_id'], ['pickster.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_audit_events_event_type',  'audit_events', ['event_type'])
        op.create_index('ix_audit_events_so_number',   'audit_events', ['so_number'])
        op.create_index('ix_audit_events_occurred_at', 'audit_events', ['occurred_at'])


def downgrade():
    # No-op: this is a catch-up migration for schema drift; reverting it would
    # require knowing which objects pre-existed, which isn't trackable here.
    pass

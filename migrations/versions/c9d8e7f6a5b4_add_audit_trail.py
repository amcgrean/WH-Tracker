"""Add audit trail: AuditEvent table, notes on Pick/WorkOrder, completed_by on WorkOrder

Revision ID: c9d8e7f6a5b4
Revises: a1c4e2f9b803
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d8e7f6a5b4'
down_revision = 'a1c4e2f9b803'
branch_labels = None
depends_on = None


def upgrade():
    # Add notes column to pick table
    op.add_column('pick', sa.Column('notes', sa.Text(), nullable=True))

    # Add notes and completed_by_id to work_orders table
    op.add_column('work_orders', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('work_orders', sa.Column('completed_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_work_orders_completed_by_id',
        'work_orders', 'pickster',
        ['completed_by_id'], ['id']
    )

    # Create audit_events table
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('so_number', sa.String(128), nullable=True),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['pickster.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_events_event_type', 'audit_events', ['event_type'])
    op.create_index('ix_audit_events_so_number', 'audit_events', ['so_number'])
    op.create_index('ix_audit_events_occurred_at', 'audit_events', ['occurred_at'])


def downgrade():
    op.drop_index('ix_audit_events_occurred_at', table_name='audit_events')
    op.drop_index('ix_audit_events_so_number', table_name='audit_events')
    op.drop_index('ix_audit_events_event_type', table_name='audit_events')
    op.drop_table('audit_events')

    op.drop_constraint('fk_work_orders_completed_by_id', 'work_orders', type_='foreignkey')
    op.drop_column('work_orders', 'completed_by_id')
    op.drop_column('work_orders', 'notes')

    op.drop_column('pick', 'notes')

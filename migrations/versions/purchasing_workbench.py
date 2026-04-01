"""add purchasing workbench tables

Revision ID: p1q2r3s4t5u6
Revises: o9p0q1r2s3t4
Create Date: 2026-03-31 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'p1q2r3s4t5u6'
down_revision = 'o9p0q1r2s3t4'
branch_labels = None
depends_on = None


def _table_exists(name):
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t AND table_schema = 'public'"
        ),
        {"t": name},
    ).fetchone()
    return row is not None


def _column_exists(table, column):
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row is not None


def upgrade():
    if _table_exists('purchasing_assignments'):
        return  # Tables already created (previous partial run or out-of-band DDL)

    op.create_table(
        'purchasing_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_code', sa.String(length=32), nullable=False),
        sa.Column('buyer_user_id', sa.Integer(), nullable=True),
        sa.Column('assigned_by_user_id', sa.Integer(), nullable=True),
        sa.Column('assignment_type', sa.String(length=32), nullable=False, server_default='branch'),
        sa.Column('supplier_key', sa.String(length=64), nullable=True),
        sa.Column('item_ptr', sa.String(length=64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['assigned_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['buyer_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_purchasing_assignments_branch_code'), 'purchasing_assignments', ['branch_code'], unique=False)
    op.create_index(op.f('ix_purchasing_assignments_buyer_user_id'), 'purchasing_assignments', ['buyer_user_id'], unique=False)
    op.create_index(op.f('ix_purchasing_assignments_active'), 'purchasing_assignments', ['active'], unique=False)

    op.create_table(
        'purchasing_work_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('queue_type', sa.String(length=32), nullable=False),
        sa.Column('reference_type', sa.String(length=32), nullable=False),
        sa.Column('reference_number', sa.String(length=128), nullable=False),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('buyer_user_id', sa.Integer(), nullable=True),
        sa.Column('supplier_key', sa.String(length=64), nullable=True),
        sa.Column('supplier_name', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='medium'),
        sa.Column('severity', sa.String(length=16), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['buyer_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['queue_type', 'reference_type', 'reference_number', 'po_number', 'branch_code', 'buyer_user_id', 'status', 'priority', 'severity', 'due_at', 'created_at']:
        op.create_index(op.f(f'ix_purchasing_work_queue_{col}'), 'purchasing_work_queue', [col], unique=False)

    op.create_table(
        'purchasing_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_internal', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['entity_type', 'entity_id', 'po_number', 'branch_code', 'created_at']:
        op.create_index(op.f(f'ix_purchasing_notes_{col}'), 'purchasing_notes', [col], unique=False)

    op.create_table(
        'purchasing_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('queue_item_id', sa.Integer(), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('assignee_user_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='medium'),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['assignee_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['queue_item_id'], ['purchasing_work_queue.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['po_number', 'queue_item_id', 'branch_code', 'assignee_user_id', 'status', 'priority', 'due_at']:
        op.create_index(op.f(f'ix_purchasing_tasks_{col}'), 'purchasing_tasks', [col], unique=False)

    op.create_table(
        'purchasing_approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('approval_type', sa.String(length=32), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('approver_user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approver_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['approval_type', 'entity_type', 'entity_id', 'po_number', 'branch_code', 'status', 'requested_at']:
        op.create_index(op.f(f'ix_purchasing_approvals_{col}'), 'purchasing_approvals', [col], unique=False)

    op.create_table(
        'purchasing_exception_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('receiving_number', sa.String(length=64), nullable=True),
        sa.Column('queue_item_id', sa.Integer(), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('supplier_key', sa.String(length=64), nullable=True),
        sa.Column('severity', sa.String(length=16), nullable=False, server_default='medium'),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['queue_item_id'], ['purchasing_work_queue.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['event_type', 'event_status', 'po_number', 'receiving_number', 'queue_item_id', 'branch_code', 'supplier_key', 'severity', 'created_at']:
        op.create_index(op.f(f'ix_purchasing_exception_events_{col}'), 'purchasing_exception_events', [col], unique=False)

    op.create_table(
        'purchasing_dashboard_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_type', sa.String(length=32), nullable=False),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('buyer_user_id', sa.Integer(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['buyer_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['snapshot_type', 'branch_code', 'buyer_user_id', 'captured_at']:
        op.create_index(op.f(f'ix_purchasing_dashboard_snapshots_{col}'), 'purchasing_dashboard_snapshots', [col], unique=False)

    op.create_table(
        'purchasing_activity',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('activity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('po_number', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['app_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['activity_type', 'entity_type', 'entity_id', 'po_number', 'branch_code', 'actor_user_id', 'created_at']:
        op.create_index(op.f(f'ix_purchasing_activity_{col}'), 'purchasing_activity', [col], unique=False)

    op.add_column('po_submissions', sa.Column('submission_type', sa.String(length=32), nullable=False, server_default='receiving_checkin'))
    op.add_column('po_submissions', sa.Column('priority', sa.String(length=16), nullable=True))
    op.add_column('po_submissions', sa.Column('queue_item_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_po_submissions_queue_item_id', 'po_submissions', 'purchasing_work_queue', ['queue_item_id'], ['id'], ondelete='SET NULL')
    op.alter_column('po_submissions', 'submission_type', server_default=None)


def downgrade():
    op.drop_constraint('fk_po_submissions_queue_item_id', 'po_submissions', type_='foreignkey')
    op.drop_column('po_submissions', 'queue_item_id')
    op.drop_column('po_submissions', 'priority')
    op.drop_column('po_submissions', 'submission_type')
    op.drop_table('purchasing_activity')
    op.drop_table('purchasing_dashboard_snapshots')
    op.drop_table('purchasing_exception_events')
    op.drop_table('purchasing_approvals')
    op.drop_table('purchasing_tasks')
    op.drop_table('purchasing_notes')
    op.drop_table('purchasing_work_queue')
    op.drop_table('purchasing_assignments')

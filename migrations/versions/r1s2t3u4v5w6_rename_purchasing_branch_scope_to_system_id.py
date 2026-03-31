"""rename purchasing branch scope columns to system_id

Revision ID: r1s2t3u4v5w6
Revises: p1q2r3s4t5u6
Create Date: 2026-03-31 21:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'r1s2t3u4v5w6'
down_revision = 'p1q2r3s4t5u6'
branch_labels = None
depends_on = None


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


def _index_exists(name):
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": name},
    ).fetchone()
    return row is not None


def _rename_branch_scope_column(table_name: str, old_index_name: str, new_index_name: str) -> None:
    if _column_exists(table_name, 'system_id'):
        return  # Already renamed
    op.alter_column(table_name, 'branch_code', new_column_name='system_id', existing_type=sa.String(length=32), existing_nullable=True)
    if _index_exists(old_index_name):
        op.drop_index(old_index_name, table_name=table_name)
    if not _index_exists(new_index_name):
        op.create_index(new_index_name, table_name, ['system_id'], unique=False)


def upgrade():
    if not _column_exists('purchasing_assignments', 'branch_code'):
        return  # Already renamed in a previous run

    op.alter_column('purchasing_assignments', 'branch_code', new_column_name='system_id', existing_type=sa.String(length=32), existing_nullable=False)
    if _index_exists('ix_purchasing_assignments_branch_code'):
        op.drop_index('ix_purchasing_assignments_branch_code', table_name='purchasing_assignments')
    if not _index_exists('ix_purchasing_assignments_system_id'):
        op.create_index('ix_purchasing_assignments_system_id', 'purchasing_assignments', ['system_id'], unique=False)

    _rename_branch_scope_column('purchasing_work_queue', 'ix_purchasing_work_queue_branch_code', 'ix_purchasing_work_queue_system_id')
    _rename_branch_scope_column('purchasing_notes', 'ix_purchasing_notes_branch_code', 'ix_purchasing_notes_system_id')
    _rename_branch_scope_column('purchasing_tasks', 'ix_purchasing_tasks_branch_code', 'ix_purchasing_tasks_system_id')
    _rename_branch_scope_column('purchasing_approvals', 'ix_purchasing_approvals_branch_code', 'ix_purchasing_approvals_system_id')
    _rename_branch_scope_column('purchasing_exception_events', 'ix_purchasing_exception_events_branch_code', 'ix_purchasing_exception_events_system_id')
    _rename_branch_scope_column('purchasing_dashboard_snapshots', 'ix_purchasing_dashboard_snapshots_branch_code', 'ix_purchasing_dashboard_snapshots_system_id')
    _rename_branch_scope_column('purchasing_activity', 'ix_purchasing_activity_branch_code', 'ix_purchasing_activity_system_id')


def downgrade():
    op.alter_column('purchasing_assignments', 'system_id', new_column_name='branch_code', existing_type=sa.String(length=32), existing_nullable=False)
    op.drop_index('ix_purchasing_assignments_system_id', table_name='purchasing_assignments')
    op.create_index('ix_purchasing_assignments_branch_code', 'purchasing_assignments', ['branch_code'], unique=False)

    for table_name, old_index_name, new_index_name in [
        ('purchasing_work_queue', 'ix_purchasing_work_queue_system_id', 'ix_purchasing_work_queue_branch_code'),
        ('purchasing_notes', 'ix_purchasing_notes_system_id', 'ix_purchasing_notes_branch_code'),
        ('purchasing_tasks', 'ix_purchasing_tasks_system_id', 'ix_purchasing_tasks_branch_code'),
        ('purchasing_approvals', 'ix_purchasing_approvals_system_id', 'ix_purchasing_approvals_branch_code'),
        ('purchasing_exception_events', 'ix_purchasing_exception_events_system_id', 'ix_purchasing_exception_events_branch_code'),
        ('purchasing_dashboard_snapshots', 'ix_purchasing_dashboard_snapshots_system_id', 'ix_purchasing_dashboard_snapshots_branch_code'),
        ('purchasing_activity', 'ix_purchasing_activity_system_id', 'ix_purchasing_activity_branch_code'),
    ]:
        op.alter_column(table_name, 'system_id', new_column_name='branch_code', existing_type=sa.String(length=32), existing_nullable=True)
        op.drop_index(old_index_name, table_name=table_name)
        op.create_index(new_index_name, table_name, ['branch_code'], unique=False)

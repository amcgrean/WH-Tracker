"""Add wo_assignments table for local WO assignment tracking

Revision ID: a2b3c4d5e6f7
Revises: b4c5d6e7f8a9
Create Date: 2026-03-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a2b3c4d5e6f7'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wo_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wo_id', sa.String(128), nullable=False),
        sa.Column('sales_order_number', sa.String(128), nullable=True),
        sa.Column('item_number', sa.String(128), nullable=True),
        sa.Column('description', sa.String(256), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('completed_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['pickster.id']),
        sa.ForeignKeyConstraint(['completed_by_id'], ['pickster.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wo_id', name='uq_wo_assignments_wo_id'),
    )
    op.create_index('ix_wo_assignments_wo_id', 'wo_assignments', ['wo_id'])
    op.create_index('ix_wo_assignments_assigned_to_id', 'wo_assignments', ['assigned_to_id'])


def downgrade():
    op.drop_index('ix_wo_assignments_assigned_to_id', table_name='wo_assignments')
    op.drop_index('ix_wo_assignments_wo_id', table_name='wo_assignments')
    op.drop_table('wo_assignments')

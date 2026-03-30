"""Create po_submissions table

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l6m7n8o9p0q1'
down_revision = 'k5l6m7n8o9p0b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'po_submissions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('po_number', sa.Text(), nullable=False),
        sa.Column('image_urls', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('supplier_name', sa.Text(), nullable=True),
        sa.Column('supplier_key', sa.Text(), nullable=True),
        sa.Column('po_status', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('submitted_by', sa.Integer(),
                  sa.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('submitted_username', sa.Text(), nullable=True),
        sa.Column('branch', sa.Text(), nullable=True),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(),
                  sa.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_po_submissions_po_number', 'po_submissions', ['po_number'])
    op.create_index('idx_po_submissions_submitted_by', 'po_submissions', ['submitted_by'])
    op.create_index('idx_po_submissions_branch', 'po_submissions', ['branch'])
    op.create_index('idx_po_submissions_status_created', 'po_submissions',
                    ['status', 'created_at'])
    op.create_index('idx_po_submissions_created_at', 'po_submissions', ['created_at'])


def downgrade():
    op.drop_index('idx_po_submissions_created_at', table_name='po_submissions')
    op.drop_index('idx_po_submissions_status_created', table_name='po_submissions')
    op.drop_index('idx_po_submissions_branch', table_name='po_submissions')
    op.drop_index('idx_po_submissions_submitted_by', table_name='po_submissions')
    op.drop_index('idx_po_submissions_po_number', table_name='po_submissions')
    op.drop_table('po_submissions')

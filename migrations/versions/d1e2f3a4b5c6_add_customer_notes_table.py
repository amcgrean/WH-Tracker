"""Add customer_notes table

Revision ID: d1e2f3a4b5c6
Revises: c9d8e7f6a5b4
Create Date: 2026-03-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c9d8e7f6a5b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customer_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_number', sa.String(50), nullable=False),
        sa.Column('note_type', sa.String(50), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('rep_name', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_customer_notes_customer_number', 'customer_notes', ['customer_number'])


def downgrade():
    op.drop_index('ix_customer_notes_customer_number', table_name='customer_notes')
    op.drop_table('customer_notes')

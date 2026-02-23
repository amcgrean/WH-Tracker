"""Add credit_images table for RMA email attachments

Revision ID: a1c4e2f9b803
Revises: 83fabbe397a1
Create Date: 2026-02-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e2f9b803'
down_revision = '83fabbe397a1'
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
    op.drop_index('ix_credit_images_rma_number', table_name='credit_images')
    op.drop_table('credit_images')

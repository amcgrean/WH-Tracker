"""Add GPS coordinates and geocoding metadata to erp_mirror_cust_shipto

Revision ID: a8f3c2d1e9b7
Revises: f3a8b9c4d5e6
Create Date: 2026-03-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8f3c2d1e9b7'
down_revision = 'f3a8b9c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('erp_mirror_cust_shipto', sa.Column('lat', sa.Numeric(precision=9, scale=6), nullable=True))
    op.add_column('erp_mirror_cust_shipto', sa.Column('lon', sa.Numeric(precision=9, scale=6), nullable=True))
    op.add_column('erp_mirror_cust_shipto', sa.Column('geocoded_at', sa.DateTime(), nullable=True))
    op.add_column('erp_mirror_cust_shipto', sa.Column('geocode_source', sa.String(length=64), nullable=True))
    op.create_index('ix_erp_mirror_cust_shipto_geocoded', 'erp_mirror_cust_shipto', ['geocoded_at'])


def downgrade():
    op.drop_index('ix_erp_mirror_cust_shipto_geocoded', table_name='erp_mirror_cust_shipto')
    op.drop_column('erp_mirror_cust_shipto', 'geocode_source')
    op.drop_column('erp_mirror_cust_shipto', 'geocoded_at')
    op.drop_column('erp_mirror_cust_shipto', 'lon')
    op.drop_column('erp_mirror_cust_shipto', 'lat')

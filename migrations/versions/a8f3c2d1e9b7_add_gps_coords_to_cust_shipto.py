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
    # Idempotent form: these columns already exist in databases where a prior partial
    # migration attempt added them before Alembic could record the revision.
    # IF NOT EXISTS ensures this migration succeeds whether or not the columns are present.
    op.execute("ALTER TABLE erp_mirror_cust_shipto ADD COLUMN IF NOT EXISTS lat NUMERIC(9,6)")
    op.execute("ALTER TABLE erp_mirror_cust_shipto ADD COLUMN IF NOT EXISTS lon NUMERIC(9,6)")
    op.execute("ALTER TABLE erp_mirror_cust_shipto ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMP")
    op.execute("ALTER TABLE erp_mirror_cust_shipto ADD COLUMN IF NOT EXISTS geocode_source VARCHAR(64)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_erp_mirror_cust_shipto_geocoded "
        "ON erp_mirror_cust_shipto (geocoded_at)"
    )


def downgrade():
    op.drop_index('ix_erp_mirror_cust_shipto_geocoded', table_name='erp_mirror_cust_shipto')
    op.drop_column('erp_mirror_cust_shipto', 'geocode_source')
    op.drop_column('erp_mirror_cust_shipto', 'geocoded_at')
    op.drop_column('erp_mirror_cust_shipto', 'lon')
    op.drop_column('erp_mirror_cust_shipto', 'lat')

"""Add pg_trgm GIN indexes for fast ILIKE text search on order lookups

Revision ID: a7b8c9d0e1f2
Revises: f9a1b2c3d4e5
Create Date: 2026-03-25 00:00:00.000000

B-tree indexes cannot accelerate ILIKE with leading wildcards (%query%).
pg_trgm GIN indexes break text into trigrams and support fast substring search.

Indexes added:
- erp_mirror_so_header:  so_id   (gin_trgm) — order number search
- erp_mirror_cust:       cust_name (gin_trgm) — customer name search
- erp_mirror_cust:       cust_code (gin_trgm) — customer code search
"""
from alembic import op


revision = 'a7b8c9d0e1f2'
down_revision = 'f9a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    # Enable the pg_trgm extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN trigram index on so_id for ILIKE '%query%' searches
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_so_header_so_id_trgm "
        "ON erp_mirror_so_header USING gin (so_id gin_trgm_ops)"
    )

    # GIN trigram index on cust_name for ILIKE '%query%' searches
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cust_name_trgm "
        "ON erp_mirror_cust USING gin (cust_name gin_trgm_ops)"
    )

    # GIN trigram index on cust_code for ILIKE '%query%' searches
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cust_code_trgm "
        "ON erp_mirror_cust USING gin (cust_code gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_cust_code_trgm")
    op.execute("DROP INDEX IF EXISTS ix_cust_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_so_header_so_id_trgm")

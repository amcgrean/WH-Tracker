"""Add composite indexes for sales dashboard query performance

Revision ID: e1f2a3b4c5d6
Revises: b4c5d6e7f8a9
Create Date: 2026-03-20 00:00:00.000000

Performance indexes added:
- erp_mirror_so_header: (so_status, expect_date) - accelerates open-order + date-range queries
- erp_mirror_so_header: (system_id, cust_key)    - accelerates customer JOIN lookups
- erp_mirror_so_header: (system_id, so_status)   - accelerates branch-filtered status queries
- erp_mirror_cust:      (cust_code, cust_name)   - accelerates type-ahead customer search
- erp_mirror_so_detail: (system_id, so_id)       - accelerates line-count sub-join
- erp_mirror_shipments_header: (system_id, so_id, invoice_date) - accelerates invoice date filter
"""
from alembic import op


revision = 'e1f2a3b4c5d6'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    # erp_mirror_so_header composite indexes
    op.create_index(
        'ix_so_header_status_expect_date',
        'erp_mirror_so_header',
        ['so_status', 'expect_date'],
        unique=False,
    )
    op.create_index(
        'ix_so_header_system_cust',
        'erp_mirror_so_header',
        ['system_id', 'cust_key'],
        unique=False,
    )
    op.create_index(
        'ix_so_header_system_status',
        'erp_mirror_so_header',
        ['system_id', 'so_status'],
        unique=False,
    )

    # erp_mirror_cust composite index for type-ahead search
    op.create_index(
        'ix_cust_code_name',
        'erp_mirror_cust',
        ['cust_code', 'cust_name'],
        unique=False,
    )

    # erp_mirror_so_detail: composite for the line-count join
    op.create_index(
        'ix_so_detail_system_so',
        'erp_mirror_so_detail',
        ['system_id', 'so_id'],
        unique=False,
    )

    # erp_mirror_shipments_header: composite for invoice date filtering
    op.create_index(
        'ix_shipments_header_system_so_invoice',
        'erp_mirror_shipments_header',
        ['system_id', 'so_id', 'invoice_date'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_shipments_header_system_so_invoice', table_name='erp_mirror_shipments_header')
    op.drop_index('ix_so_detail_system_so', table_name='erp_mirror_so_detail')
    op.drop_index('ix_cust_code_name', table_name='erp_mirror_cust')
    op.drop_index('ix_so_header_system_status', table_name='erp_mirror_so_header')
    op.drop_index('ix_so_header_system_cust', table_name='erp_mirror_so_header')
    op.drop_index('ix_so_header_status_expect_date', table_name='erp_mirror_so_header')

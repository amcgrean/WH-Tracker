"""Add additional mirror table indexes for is_deleted filters and join patterns

Revision ID: f9a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-03-25 00:00:00.000000

Performance indexes added:
- erp_mirror_so_header:        (is_deleted, so_status) — all open-order queries now filter both
- erp_mirror_wo_header:        (source_id, is_deleted) — work-order-by-SO lookup
- erp_mirror_cust_shipto:      (cust_key, seq_num)     — dispatch stop address join
- erp_mirror_shipments_header: (so_id, ship_date)      — delivery tracker date queries
- erp_mirror_pick_detail:      (tran_type, tran_id)    — pick ticket SO join
- erp_mirror_aropen:           (cust_key, open_flag)   — AR aging per customer
"""
from alembic import op


revision = 'f9a1b2c3d4e5'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    # erp_mirror_so_header: cover is_deleted + so_status (used in every open-order query)
    op.create_index(
        'ix_so_header_deleted_status',
        'erp_mirror_so_header',
        ['is_deleted', 'so_status'],
        unique=False,
    )

    # erp_mirror_wo_header: work order lookup by source SO
    op.create_index(
        'ix_wo_header_source_deleted',
        'erp_mirror_wo_header',
        ['source_id', 'is_deleted'],
        unique=False,
    )

    # erp_mirror_cust_shipto: dispatch stop address join (cust_key + seq_num is the natural key)
    op.create_index(
        'ix_cust_shipto_key_seq',
        'erp_mirror_cust_shipto',
        ['cust_key', 'seq_num'],
        unique=False,
    )

    # erp_mirror_shipments_header: delivery tracker date-range queries
    op.create_index(
        'ix_shipments_header_so_ship_date',
        'erp_mirror_shipments_header',
        ['so_id', 'ship_date'],
        unique=False,
    )

    # erp_mirror_pick_detail: pick ticket SO join by transaction type + id
    op.create_index(
        'ix_pick_detail_tran_type_id',
        'erp_mirror_pick_detail',
        ['tran_type', 'tran_id'],
        unique=False,
    )

    # erp_mirror_aropen: AR aging per customer filtered by open_flag
    op.create_index(
        'ix_aropen_cust_open',
        'erp_mirror_aropen',
        ['cust_key', 'open_flag'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_aropen_cust_open', table_name='erp_mirror_aropen')
    op.drop_index('ix_pick_detail_tran_type_id', table_name='erp_mirror_pick_detail')
    op.drop_index('ix_shipments_header_so_ship_date', table_name='erp_mirror_shipments_header')
    op.drop_index('ix_cust_shipto_key_seq', table_name='erp_mirror_cust_shipto')
    op.drop_index('ix_wo_header_source_deleted', table_name='erp_mirror_wo_header')
    op.drop_index('ix_so_header_deleted_status', table_name='erp_mirror_so_header')

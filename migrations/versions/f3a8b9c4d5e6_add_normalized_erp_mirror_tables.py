"""Add normalized ERP mirror tables and sync metadata

Revision ID: f3a8b9c4d5e6
Revises: a1c4e2f9b803
Create Date: 2026-03-17 13:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a8b9c4d5e6'
down_revision = 'a1c4e2f9b803'
branch_labels = None
depends_on = None


def add_sync_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column('source_updated_at', sa.DateTime(), nullable=True))
    op.add_column(table_name, sa.Column('sync_batch_id', sa.String(length=64), nullable=True))
    op.add_column(table_name, sa.Column('row_fingerprint', sa.String(length=64), nullable=True))
    op.add_column(table_name, sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(f'ix_{table_name}_source_updated_at', table_name, ['source_updated_at'])
    op.create_index(f'ix_{table_name}_sync_batch_id', table_name, ['sync_batch_id'])
    op.create_index(f'ix_{table_name}_is_deleted', table_name, ['is_deleted'])


def drop_sync_columns(table_name: str) -> None:
    op.drop_index(f'ix_{table_name}_is_deleted', table_name=table_name)
    op.drop_index(f'ix_{table_name}_sync_batch_id', table_name=table_name)
    op.drop_index(f'ix_{table_name}_source_updated_at', table_name=table_name)
    op.drop_column(table_name, 'is_deleted')
    op.drop_column(table_name, 'row_fingerprint')
    op.drop_column(table_name, 'sync_batch_id')
    op.drop_column(table_name, 'source_updated_at')


def upgrade():
    op.create_table(
        'erp_sync_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('worker_name', sa.String(length=128), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('family', sa.String(length=32), nullable=True),
        sa.Column('table_count', sa.Integer(), nullable=False),
        sa.Column('rows_extracted', sa.Integer(), nullable=False),
        sa.Column('rows_staged', sa.Integer(), nullable=False),
        sa.Column('rows_upserted', sa.Integer(), nullable=False),
        sa.Column('rows_deleted', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id'),
    )
    op.create_index('ix_erp_sync_batches_batch_id', 'erp_sync_batches', ['batch_id'])
    op.create_index('ix_erp_sync_batches_worker_name', 'erp_sync_batches', ['worker_name'])
    op.create_index('ix_erp_sync_batches_family', 'erp_sync_batches', ['family'])

    op.create_table(
        'erp_sync_table_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('table_name', sa.String(length=128), nullable=False),
        sa.Column('family', sa.String(length=32), nullable=False),
        sa.Column('strategy', sa.String(length=32), nullable=False),
        sa.Column('last_batch_id', sa.String(length=64), nullable=True),
        sa.Column('last_status', sa.String(length=32), nullable=False),
        sa.Column('last_success_at', sa.DateTime(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_source_updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_row_count', sa.Integer(), nullable=False),
        sa.Column('last_duration_ms', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('table_name'),
    )
    op.create_index('ix_erp_sync_table_state_table_name', 'erp_sync_table_state', ['table_name'])
    op.create_index('ix_erp_sync_table_state_family', 'erp_sync_table_state', ['family'])
    op.create_index('ix_erp_sync_table_state_last_batch_id', 'erp_sync_table_state', ['last_batch_id'])

    op.create_table(
        'erp_mirror_cust',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cust_key', sa.String(length=64), nullable=False),
        sa.Column('cust_code', sa.String(length=64), nullable=False),
        sa.Column('cust_name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('balance', sa.Numeric(18, 2), nullable=True),
        sa.Column('credit_limit', sa.Numeric(18, 2), nullable=True),
        sa.Column('credit_account', sa.Boolean(), nullable=True),
        sa.Column('cust_type', sa.String(length=32), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cust_key', name='uq_erp_mirror_cust_key'),
    )
    op.create_index('ix_erp_mirror_cust_cust_key', 'erp_mirror_cust', ['cust_key'])
    op.create_index('ix_erp_mirror_cust_cust_code', 'erp_mirror_cust', ['cust_code'])
    op.create_index('ix_erp_mirror_cust_synced_at', 'erp_mirror_cust', ['synced_at'])
    op.create_index('ix_erp_mirror_cust_branch_code', 'erp_mirror_cust', ['branch_code'])
    add_sync_columns('erp_mirror_cust')

    op.create_table(
        'erp_mirror_cust_shipto',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cust_key', sa.String(length=64), nullable=False),
        sa.Column('seq_num', sa.String(length=32), nullable=False),
        sa.Column('shipto_name', sa.String(length=255), nullable=True),
        sa.Column('address_1', sa.String(length=255), nullable=True),
        sa.Column('address_2', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=128), nullable=True),
        sa.Column('state', sa.String(length=32), nullable=True),
        sa.Column('zip', sa.String(length=32), nullable=True),
        sa.Column('attention', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cust_key', 'seq_num', name='uq_erp_mirror_cust_shipto_key'),
    )
    op.create_index('ix_erp_mirror_cust_shipto_cust_key', 'erp_mirror_cust_shipto', ['cust_key'])
    op.create_index('ix_erp_mirror_cust_shipto_branch_code', 'erp_mirror_cust_shipto', ['branch_code'])
    op.create_index('ix_erp_mirror_cust_shipto_synced_at', 'erp_mirror_cust_shipto', ['synced_at'])
    add_sync_columns('erp_mirror_cust_shipto')

    op.create_table(
        'erp_mirror_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_ptr', sa.String(length=64), nullable=False),
        sa.Column('item', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('stocking_uom', sa.String(length=32), nullable=True),
        sa.Column('item_group', sa.String(length=64), nullable=True),
        sa.Column('product_line', sa.String(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_ptr', name='uq_erp_mirror_item_ptr'),
    )
    op.create_index('ix_erp_mirror_item_item_ptr', 'erp_mirror_item', ['item_ptr'])
    op.create_index('ix_erp_mirror_item_item', 'erp_mirror_item', ['item'])
    op.create_index('ix_erp_mirror_item_synced_at', 'erp_mirror_item', ['synced_at'])
    add_sync_columns('erp_mirror_item')

    op.create_table(
        'erp_mirror_item_branch',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('item_ptr', sa.String(length=64), nullable=False),
        sa.Column('handling_code', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('qty_on_hand', sa.Numeric(18, 4), nullable=True),
        sa.Column('qty_available', sa.Numeric(18, 4), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'item_ptr', name='uq_erp_mirror_item_branch_key'),
    )
    op.create_index('ix_erp_mirror_item_branch_system_id', 'erp_mirror_item_branch', ['system_id'])
    op.create_index('ix_erp_mirror_item_branch_item_ptr', 'erp_mirror_item_branch', ['item_ptr'])
    op.create_index('ix_erp_mirror_item_branch_branch_code', 'erp_mirror_item_branch', ['branch_code'])
    op.create_index('ix_erp_mirror_item_branch_synced_at', 'erp_mirror_item_branch', ['synced_at'])
    add_sync_columns('erp_mirror_item_branch')

    op.create_table(
        'erp_mirror_item_uomconv',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_ptr', sa.String(length=64), nullable=False),
        sa.Column('uom_ptr', sa.String(length=64), nullable=False),
        sa.Column('conv_factor_from_stocking', sa.Numeric(18, 6), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_ptr', 'uom_ptr', name='uq_erp_mirror_item_uomconv_key'),
    )
    op.create_index('ix_erp_mirror_item_uomconv_item_ptr', 'erp_mirror_item_uomconv', ['item_ptr'])
    op.create_index('ix_erp_mirror_item_uomconv_synced_at', 'erp_mirror_item_uomconv', ['synced_at'])
    add_sync_columns('erp_mirror_item_uomconv')

    op.create_table(
        'erp_mirror_so_header',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('so_id', sa.String(length=64), nullable=False),
        sa.Column('so_status', sa.String(length=16), nullable=True),
        sa.Column('sale_type', sa.String(length=32), nullable=True),
        sa.Column('cust_key', sa.String(length=64), nullable=True),
        sa.Column('shipto_seq_num', sa.String(length=32), nullable=True),
        sa.Column('reference', sa.String(length=255), nullable=True),
        sa.Column('expect_date', sa.DateTime(), nullable=True),
        sa.Column('created_date', sa.DateTime(), nullable=True),
        sa.Column('invoice_date', sa.DateTime(), nullable=True),
        sa.Column('ship_date', sa.DateTime(), nullable=True),
        sa.Column('promise_date', sa.DateTime(), nullable=True),
        sa.Column('ship_via', sa.String(length=128), nullable=True),
        sa.Column('terms', sa.String(length=64), nullable=True),
        sa.Column('salesperson', sa.String(length=64), nullable=True),
        sa.Column('po_number', sa.String(length=128), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'so_id', name='uq_erp_mirror_so_header_key'),
    )
    for name in ['system_id', 'so_id', 'so_status', 'cust_key', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_so_header_{name}', 'erp_mirror_so_header', [name])
    add_sync_columns('erp_mirror_so_header')

    op.create_table(
        'erp_mirror_so_detail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('so_id', sa.String(length=64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('item_ptr', sa.String(length=64), nullable=True),
        sa.Column('qty_ordered', sa.Numeric(18, 4), nullable=True),
        sa.Column('qty_shipped', sa.Numeric(18, 4), nullable=True),
        sa.Column('backordered_qty', sa.Numeric(18, 4), nullable=True),
        sa.Column('date_required', sa.DateTime(), nullable=True),
        sa.Column('price', sa.Numeric(18, 4), nullable=True),
        sa.Column('price_uom_ptr', sa.String(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'so_id', 'sequence', name='uq_erp_mirror_so_detail_key'),
    )
    for name in ['system_id', 'so_id', 'item_ptr', 'synced_at']:
        op.create_index(f'ix_erp_mirror_so_detail_{name}', 'erp_mirror_so_detail', [name])
    add_sync_columns('erp_mirror_so_detail')

    op.create_table(
        'erp_mirror_shipments_header',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('so_id', sa.String(length=64), nullable=False),
        sa.Column('shipment_num', sa.String(length=64), nullable=False),
        sa.Column('status_flag', sa.String(length=16), nullable=True),
        sa.Column('status_flag_delivery', sa.String(length=16), nullable=True),
        sa.Column('invoice_date', sa.DateTime(), nullable=True),
        sa.Column('ship_date', sa.DateTime(), nullable=True),
        sa.Column('loaded_date', sa.DateTime(), nullable=True),
        sa.Column('loaded_time', sa.String(length=32), nullable=True),
        sa.Column('route_id_char', sa.String(length=64), nullable=True),
        sa.Column('ship_via', sa.String(length=128), nullable=True),
        sa.Column('driver', sa.String(length=128), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'so_id', 'shipment_num', name='uq_erp_mirror_shipments_header_key'),
    )
    for name in ['system_id', 'so_id', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_shipments_header_{name}', 'erp_mirror_shipments_header', [name])
    add_sync_columns('erp_mirror_shipments_header')

    op.create_table(
        'erp_mirror_shipments_detail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('so_id', sa.String(length=64), nullable=False),
        sa.Column('shipment_num', sa.String(length=64), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False),
        sa.Column('item_ptr', sa.String(length=64), nullable=True),
        sa.Column('qty', sa.Numeric(18, 4), nullable=True),
        sa.Column('qty_ordered', sa.Numeric(18, 4), nullable=True),
        sa.Column('qty_shipped', sa.Numeric(18, 4), nullable=True),
        sa.Column('price', sa.Numeric(18, 4), nullable=True),
        sa.Column('price_uom_ptr', sa.String(length=64), nullable=True),
        sa.Column('weight', sa.Numeric(18, 4), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'so_id', 'shipment_num', 'line_no', name='uq_erp_mirror_shipments_detail_key'),
    )
    for name in ['system_id', 'so_id', 'item_ptr', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_shipments_detail_{name}', 'erp_mirror_shipments_detail', [name])
    add_sync_columns('erp_mirror_shipments_detail')

    op.create_table(
        'erp_mirror_wo_header',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wo_id', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('source_id', sa.String(length=64), nullable=True),
        sa.Column('source_seq', sa.Integer(), nullable=True),
        sa.Column('wo_status', sa.String(length=64), nullable=True),
        sa.Column('wo_rule', sa.String(length=64), nullable=True),
        sa.Column('item_ptr', sa.String(length=64), nullable=True),
        sa.Column('qty', sa.Numeric(18, 4), nullable=True),
        sa.Column('department', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wo_id', name='uq_erp_mirror_wo_header_key'),
    )
    for name in ['wo_id', 'source_id', 'wo_status', 'item_ptr', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_wo_header_{name}', 'erp_mirror_wo_header', [name])
    add_sync_columns('erp_mirror_wo_header')

    op.create_table(
        'erp_mirror_pick_header',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pick_id', sa.String(length=64), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('created_date', sa.DateTime(), nullable=True),
        sa.Column('created_time', sa.String(length=32), nullable=True),
        sa.Column('print_status', sa.String(length=64), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pick_id', 'system_id', name='uq_erp_mirror_pick_header_key'),
    )
    for name in ['pick_id', 'system_id', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_pick_header_{name}', 'erp_mirror_pick_header', [name])
    add_sync_columns('erp_mirror_pick_header')

    op.create_table(
        'erp_mirror_pick_detail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pick_id', sa.String(length=64), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=False),
        sa.Column('tran_type', sa.String(length=32), nullable=False),
        sa.Column('tran_id', sa.String(length=64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=True),
        sa.Column('branch_code', sa.String(length=32), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pick_id', 'system_id', 'tran_type', 'tran_id', 'sequence', name='uq_erp_mirror_pick_detail_key'),
    )
    for name in ['pick_id', 'system_id', 'tran_id', 'branch_code', 'synced_at']:
        op.create_index(f'ix_erp_mirror_pick_detail_{name}', 'erp_mirror_pick_detail', [name])
    add_sync_columns('erp_mirror_pick_detail')

    op.create_table(
        'erp_mirror_aropen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ref_num', sa.String(length=64), nullable=False),
        sa.Column('cust_key', sa.String(length=64), nullable=True),
        sa.Column('ref_date', sa.DateTime(), nullable=True),
        sa.Column('update_date', sa.DateTime(), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('open_amt', sa.Numeric(18, 2), nullable=True),
        sa.Column('ref_type', sa.String(length=16), nullable=True),
        sa.Column('shipto_seq', sa.String(length=32), nullable=True),
        sa.Column('statement_id', sa.String(length=64), nullable=True),
        sa.Column('discount_amt', sa.Numeric(18, 2), nullable=True),
        sa.Column('discount_taken', sa.Numeric(18, 2), nullable=True),
        sa.Column('ref_num_sysid', sa.String(length=32), nullable=True),
        sa.Column('paid_in_full_date', sa.DateTime(), nullable=True),
        sa.Column('open_flag', sa.Boolean(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref_num', name='uq_erp_mirror_aropen_key'),
    )
    for name in ['ref_num', 'cust_key', 'ref_num_sysid', 'synced_at']:
        op.create_index(f'ix_erp_mirror_aropen_{name}', 'erp_mirror_aropen', [name])
    add_sync_columns('erp_mirror_aropen')

    op.create_table(
        'erp_mirror_aropendt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ref_num', sa.String(length=64), nullable=False),
        sa.Column('tran_id', sa.String(length=64), nullable=True),
        sa.Column('ref_num_seq', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref_num', 'tran_id', 'ref_num_seq', name='uq_erp_mirror_aropendt_key'),
    )
    for name in ['ref_num', 'tran_id', 'synced_at']:
        op.create_index(f'ix_erp_mirror_aropendt_{name}', 'erp_mirror_aropendt', [name])
    add_sync_columns('erp_mirror_aropendt')

    op.create_table(
        'erp_mirror_print_transaction',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tran_id', sa.String(length=64), nullable=False),
        sa.Column('tran_type', sa.String(length=64), nullable=False),
        sa.Column('system_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tran_id', 'tran_type', name='uq_erp_mirror_print_transaction_key'),
    )
    for name in ['tran_id', 'tran_type', 'system_id', 'synced_at']:
        op.create_index(f'ix_erp_mirror_print_transaction_{name}', 'erp_mirror_print_transaction', [name])
    add_sync_columns('erp_mirror_print_transaction')

    op.create_table(
        'erp_mirror_print_transaction_detail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tran_id', sa.String(length=64), nullable=False),
        sa.Column('printer_id', sa.String(length=64), nullable=True),
        sa.Column('printer_destination', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tran_id', 'printer_id', 'printer_destination', name='uq_erp_mirror_print_transaction_detail_key'),
    )
    for name in ['tran_id', 'printer_destination', 'synced_at']:
        op.create_index(f'ix_erp_mirror_print_transaction_detail_{name}', 'erp_mirror_print_transaction_detail', [name])
    add_sync_columns('erp_mirror_print_transaction_detail')


def downgrade():
    for table_name in [
        'erp_mirror_print_transaction_detail',
        'erp_mirror_print_transaction',
        'erp_mirror_aropendt',
        'erp_mirror_aropen',
        'erp_mirror_pick_detail',
        'erp_mirror_pick_header',
        'erp_mirror_wo_header',
        'erp_mirror_shipments_detail',
        'erp_mirror_shipments_header',
        'erp_mirror_so_detail',
        'erp_mirror_so_header',
        'erp_mirror_item_uomconv',
        'erp_mirror_item_branch',
        'erp_mirror_item',
        'erp_mirror_cust_shipto',
        'erp_mirror_cust',
    ]:
        drop_sync_columns(table_name)
        op.drop_table(table_name)

    op.drop_index('ix_erp_sync_table_state_last_batch_id', table_name='erp_sync_table_state')
    op.drop_index('ix_erp_sync_table_state_family', table_name='erp_sync_table_state')
    op.drop_index('ix_erp_sync_table_state_table_name', table_name='erp_sync_table_state')
    op.drop_table('erp_sync_table_state')

    op.drop_index('ix_erp_sync_batches_family', table_name='erp_sync_batches')
    op.drop_index('ix_erp_sync_batches_worker_name', table_name='erp_sync_batches')
    op.drop_index('ix_erp_sync_batches_batch_id', table_name='erp_sync_batches')
    op.drop_table('erp_sync_batches')

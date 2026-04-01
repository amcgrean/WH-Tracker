"""Add dispatch planning tables (routes, stops, drivers, truck assignments)

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'm7n8o9p0q1r2'
down_revision = 'l6m7n8o9p0q1'
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        return False
    return any(index.get("name") == index_name for index in indexes)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade():
    # --- DispatchDriver (roster) ---
    if not _table_exists('dispatch_drivers'):
        op.create_table(
            'dispatch_drivers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(128), nullable=False, unique=True),
            sa.Column('phone', sa.String(32), nullable=True),
            sa.Column('default_truck_id', sa.String(128), nullable=True),
            sa.Column('branch_code', sa.String(32), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing('ix_dispatch_drivers_branch_code', 'dispatch_drivers', ['branch_code'])

    # --- DispatchRoute ---
    if not _table_exists('dispatch_routes'):
        op.create_table(
            'dispatch_routes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('route_date', sa.Date(), nullable=False),
            sa.Column('route_name', sa.String(64), nullable=False),
            sa.Column('branch_code', sa.String(32), nullable=False),
            sa.Column('driver_name', sa.String(128), nullable=True),
            sa.Column('truck_id', sa.String(64), nullable=True),
            sa.Column('status', sa.String(32), nullable=False, server_default='draft'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('app_users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing('ix_dispatch_routes_route_date', 'dispatch_routes', ['route_date'])
    _create_index_if_missing('ix_dispatch_routes_branch_code', 'dispatch_routes', ['branch_code'])

    # --- DispatchRouteStop ---
    if not _table_exists('dispatch_route_stops'):
        op.create_table(
            'dispatch_route_stops',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('route_id', sa.Integer(), sa.ForeignKey('dispatch_routes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('so_id', sa.String(64), nullable=False),
            sa.Column('shipment_num', sa.String(64), nullable=True),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing('ix_dispatch_route_stops_route_id', 'dispatch_route_stops', ['route_id'])

    # --- DispatchTruckAssignment ---
    if not _table_exists('dispatch_truck_assignments'):
        op.create_table(
            'dispatch_truck_assignments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('assignment_date', sa.Date(), nullable=False),
            sa.Column('branch_code', sa.String(32), nullable=False),
            sa.Column('samsara_vehicle_id', sa.String(128), nullable=False),
            sa.Column('samsara_vehicle_name', sa.String(255), nullable=True),
            sa.Column('driver_id', sa.Integer(), sa.ForeignKey('dispatch_drivers.id'), nullable=True),
            sa.Column('route_id', sa.Integer(), sa.ForeignKey('dispatch_routes.id'), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('app_users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('assignment_date', 'samsara_vehicle_id', name='uq_dispatch_truck_assignment_date_vehicle'),
        )
    _create_index_if_missing('ix_dispatch_truck_assignments_date', 'dispatch_truck_assignments', ['assignment_date'])
    _create_index_if_missing('ix_dispatch_truck_assignments_branch', 'dispatch_truck_assignments', ['branch_code'])


def downgrade():
    if _table_exists('dispatch_truck_assignments'):
        op.drop_table('dispatch_truck_assignments')
    if _table_exists('dispatch_route_stops'):
        op.drop_table('dispatch_route_stops')
    if _table_exists('dispatch_routes'):
        op.drop_table('dispatch_routes')
    if _table_exists('dispatch_drivers'):
        op.drop_table('dispatch_drivers')

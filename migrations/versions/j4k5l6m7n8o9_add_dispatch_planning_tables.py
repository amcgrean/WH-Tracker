"""Add dispatch planning tables (routes, stops, drivers, truck assignments)

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-03-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'j4k5l6m7n8o9'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None


def upgrade():
    # --- DispatchDriver (roster) ---
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
    op.create_index('ix_dispatch_drivers_branch_code', 'dispatch_drivers', ['branch_code'])

    # --- DispatchRoute ---
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
    op.create_index('ix_dispatch_routes_route_date', 'dispatch_routes', ['route_date'])
    op.create_index('ix_dispatch_routes_branch_code', 'dispatch_routes', ['branch_code'])

    # --- DispatchRouteStop ---
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
    op.create_index('ix_dispatch_route_stops_route_id', 'dispatch_route_stops', ['route_id'])

    # --- DispatchTruckAssignment ---
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
    op.create_index('ix_dispatch_truck_assignments_date', 'dispatch_truck_assignments', ['assignment_date'])
    op.create_index('ix_dispatch_truck_assignments_branch', 'dispatch_truck_assignments', ['branch_code'])


def downgrade():
    op.drop_table('dispatch_truck_assignments')
    op.drop_table('dispatch_route_stops')
    op.drop_table('dispatch_routes')
    op.drop_table('dispatch_drivers')

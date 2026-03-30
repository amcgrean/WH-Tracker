"""Local dispatch planning models — route planning, driver roster, truck assignments.

These are NOT ERP mirrors. They represent the dispatcher's planning intent
before anything is pushed to Agility.
"""

from datetime import datetime, date

from app.extensions import db


class DispatchRoute(db.Model):
    """A named route for a specific date — a container for ordered stops."""

    __tablename__ = "dispatch_routes"

    id = db.Column(db.Integer, primary_key=True)
    route_date = db.Column(db.Date, nullable=False, index=True)
    route_name = db.Column(db.String(64), nullable=False)
    branch_code = db.Column(db.String(32), nullable=False, index=True)
    driver_name = db.Column(db.String(128), nullable=True)
    truck_id = db.Column(db.String(64), nullable=True)  # Samsara vehicle ID
    status = db.Column(db.String(32), nullable=False, default="draft")
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    stops = db.relationship(
        "DispatchRouteStop",
        backref="route",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="DispatchRouteStop.sequence",
    )

    VALID_STATUSES = ("draft", "planned", "dispatched", "in_progress", "completed")

    def to_dict(self):
        return {
            "id": self.id,
            "route_date": self.route_date.isoformat() if self.route_date else None,
            "route_name": self.route_name,
            "branch_code": self.branch_code,
            "driver_name": self.driver_name,
            "truck_id": self.truck_id,
            "status": self.status,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "stop_count": len(self.stops) if self.stops else 0,
            "stops": [s.to_dict() for s in self.stops] if self.stops else [],
        }


class DispatchRouteStop(db.Model):
    """An ordered stop within a route — references a sales order/shipment."""

    __tablename__ = "dispatch_route_stops"

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(
        db.Integer,
        db.ForeignKey("dispatch_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    so_id = db.Column(db.String(64), nullable=False)
    shipment_num = db.Column(db.String(64), nullable=True)
    sequence = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    VALID_STATUSES = ("pending", "picked", "staged", "loaded", "delivered", "skipped")

    def to_dict(self):
        return {
            "id": self.id,
            "route_id": self.route_id,
            "so_id": self.so_id,
            "shipment_num": self.shipment_num,
            "sequence": self.sequence,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DispatchDriver(db.Model):
    """Local driver roster — managed by dispatchers, not synced from ERP."""

    __tablename__ = "dispatch_drivers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    phone = db.Column(db.String(32), nullable=True)
    default_truck_id = db.Column(
        db.String(128), nullable=True
    )  # Samsara vehicle ID they usually drive
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "default_truck_id": self.default_truck_id,
            "branch_code": self.branch_code,
            "is_active": self.is_active,
            "notes": self.notes,
        }


class DispatchTruckAssignment(db.Model):
    """Daily truck assignment board — maps Samsara trucks to drivers and routes."""

    __tablename__ = "dispatch_truck_assignments"

    id = db.Column(db.Integer, primary_key=True)
    assignment_date = db.Column(db.Date, nullable=False, index=True)
    branch_code = db.Column(db.String(32), nullable=False, index=True)
    samsara_vehicle_id = db.Column(db.String(128), nullable=False)
    samsara_vehicle_name = db.Column(db.String(255), nullable=True)
    driver_id = db.Column(
        db.Integer, db.ForeignKey("dispatch_drivers.id"), nullable=True
    )
    route_id = db.Column(
        db.Integer, db.ForeignKey("dispatch_routes.id"), nullable=True
    )
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    driver = db.relationship("DispatchDriver", backref="truck_assignments", lazy=True)
    route = db.relationship("DispatchRoute", backref="truck_assignments", lazy=True)

    __table_args__ = (
        db.UniqueConstraint(
            "assignment_date",
            "samsara_vehicle_id",
            name="uq_dispatch_truck_assignment_date_vehicle",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_date": (
                self.assignment_date.isoformat() if self.assignment_date else None
            ),
            "branch_code": self.branch_code,
            "samsara_vehicle_id": self.samsara_vehicle_id,
            "samsara_vehicle_name": self.samsara_vehicle_name,
            "driver_id": self.driver_id,
            "driver_name": self.driver.name if self.driver else None,
            "driver_phone": self.driver.phone if self.driver else None,
            "route_id": self.route_id,
            "route_name": self.route.route_name if self.route else None,
            "notes": self.notes,
        }

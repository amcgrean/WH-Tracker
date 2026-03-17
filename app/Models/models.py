from app.extensions import db
from datetime import datetime  # If you're using datetime for the DateTime columns


class Pickster(db.Model):
    __tablename__ = 'pickster'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    user_type = db.Column(db.String(50), default='picker') # 'picker', 'door_builder', etc.
    picks = db.relationship('Pick', backref='pickster', lazy=True)
    # 'picks' establishes a relationship to the Pick model, with a back-reference to 'pickster'
    # 'lazy=True' specifies that the related objects are loaded as necessary

class Pick(db.Model):
    __tablename__ = 'pick'
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_time = db.Column(db.DateTime, index=True)
    barcode_number = db.Column(db.String(120), nullable=False)
    picker_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=False)
    pick_type_id = db.Column(db.Integer, db.ForeignKey('PickTypes.pick_type_id'))
    notes = db.Column(db.Text)

class PickTypes(db.Model):
    __tablename__ = 'PickTypes'
    pick_type_id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(128),unique=True, nullable=False)


class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    sales_order_number = db.Column(db.String(128), nullable=False)
    work_order_number = db.Column(db.String(128), nullable=False, unique=True)
    item_number = db.Column(db.String(128))
    description = db.Column(db.String(256))
    status = db.Column(db.String(50), default='Open')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('pickster.id'))
    completed_by_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    assigned_to = db.relationship('Pickster', foreign_keys=[assigned_to_id], backref=db.backref('work_orders', lazy=True))
    completed_by = db.relationship('Pickster', foreign_keys=[completed_by_id], backref=db.backref('completed_work_orders', lazy=True))


class PickAssignment(db.Model):
    __tablename__ = 'pick_assignments'
    id = db.Column(db.Integer, primary_key=True)
    so_number = db.Column(db.String(50), nullable=False) # Sales Order Number
    handling_code = db.Column(db.String(50), nullable=True) # Optional: Assign per code?
    picker_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    picker = db.relationship('Pickster', backref=db.backref('assignments', lazy=True))



# -------------------------------------------------------------------
# Cloud Sync Mirrors
# These tables store a copy of the open ERP data for the cloud instance.
# -------------------------------------------------------------------

class ERPMirrorPick(db.Model):
    __tablename__ = 'erp_mirror_picks'
    id = db.Column(db.Integer, primary_key=True)
    so_number = db.Column(db.String(128), index=True)
    customer_name = db.Column(db.String(256))
    address = db.Column(db.String(256))
    reference = db.Column(db.String(256))
    handling_code = db.Column(db.String(50))
    sequence = db.Column(db.Integer)
    item_number = db.Column(db.String(128))
    description = db.Column(db.String(256))
    qty = db.Column(db.Float)
    line_count = db.Column(db.Integer)
    so_status = db.Column(db.String(10))
    shipment_status = db.Column(db.String(10))
    system_id = db.Column(db.String(50))
    expect_date = db.Column(db.String(50))
    sale_type = db.Column(db.String(50))
    local_pick_state = db.Column(db.String(50)) # NEW: Tracks local app pick status (Pick Printed, Picking, Picking Complete)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)
    # NEW fields for features 
    ship_via = db.Column(db.String(128))
    driver = db.Column(db.String(128))
    route = db.Column(db.String(128))
    printed_at = db.Column(db.DateTime, nullable=True) # Pick printed timestamp
    staged_at = db.Column(db.DateTime, nullable=True)  # Loaded/Staged timestamp
    delivered_at = db.Column(db.DateTime, nullable=True) # Delivered timestamp
    
class ERPMirrorWorkOrder(db.Model):
    __tablename__ = 'erp_mirror_work_orders'
    id = db.Column(db.Integer, primary_key=True)
    wo_id = db.Column(db.String(128), index=True)
    so_number = db.Column(db.String(128))
    description = db.Column(db.String(256))
    item_number = db.Column(db.String(128))
    status = db.Column(db.String(50))
    qty = db.Column(db.Integer)
    department = db.Column(db.String(50))
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------------------------------------------------------
# Credit / RMA Image Tracking
# Sales people email photos of credits; the poller saves them here
# so dispatchers can view them on the portal.
# -------------------------------------------------------------------

class CreditImage(db.Model):
    __tablename__ = 'credit_images'
    id            = db.Column(db.Integer, primary_key=True)
    rma_number    = db.Column(db.String(20), index=True, nullable=False)
    filename      = db.Column(db.String(256), nullable=False)
    filepath      = db.Column(db.String(512), nullable=False)  # relative to UPLOAD_FOLDER
    email_from    = db.Column(db.String(256))
    email_subject = db.Column(db.String(512))
    received_at   = db.Column(db.DateTime)   # when the email arrived
    uploaded_at   = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------------------------------------------------------
# Sales Team — Customer Notes / Call Log
# Sales reps log calls, visits, emails, and follow-ups here.
# -------------------------------------------------------------------

class CustomerNote(db.Model):
    __tablename__ = 'customer_notes'
    id              = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(db.String(50), index=True, nullable=False)
    note_type       = db.Column(db.String(50), default='Call')   # Call, Visit, Email, Issue, etc.
    body            = db.Column(db.Text, nullable=False)
    rep_name        = db.Column(db.String(128))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)


class ERPDeliveryKPI(db.Model):
    __tablename__ = 'erp_delivery_kpis'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, index=True, nullable=False)
    count = db.Column(db.Integer, nullable=False)
    branch = db.Column(db.String(50), nullable=True) # 'all', '20gr', etc.
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------------------------------------------------------
# Audit Trail
# Records key state transitions: pick started/completed, WO completed,
# staged confirmed, SO assigned, etc.
# -------------------------------------------------------------------

class AuditEvent(db.Model):
    __tablename__ = 'audit_events'
    id = db.Column(db.Integer, primary_key=True)
    # e.g. 'pick_started', 'pick_completed', 'wo_completed', 'staged_confirmed', 'pick_assigned'
    event_type = db.Column(db.String(50), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False)  # 'pick', 'work_order', 'erp_mirror_pick'
    entity_id = db.Column(db.Integer)
    so_number = db.Column(db.String(128), index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=True)
    notes = db.Column(db.Text)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    actor = db.relationship('Pickster', backref=db.backref('audit_events', lazy=True))

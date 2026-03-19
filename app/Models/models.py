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
    status_flag_delivery = db.Column(db.String(10)) # NEW: Granular delivery status from shipments_header
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
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    geocode_status = db.Column(db.String(50), nullable=True) # 'exact', 'fuzzy', 'failed'

    
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


class ERPSyncState(db.Model):
    __tablename__ = 'erp_sync_state'
    id = db.Column(db.Integer, primary_key=True)
    worker_name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    worker_mode = db.Column(db.String(50), nullable=False, default='pi')
    source_mode = db.Column(db.String(50), nullable=False, default='local_sql')
    target_mode = db.Column(db.String(50), nullable=False, default='mirror')
    interval_seconds = db.Column(db.Integer, nullable=False, default=5)
    change_monitoring = db.Column(db.Boolean, nullable=False, default=True)
    last_heartbeat_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(50), nullable=False, default='starting')
    last_error = db.Column(db.Text, nullable=True)
    last_change_token = db.Column(db.String(128), nullable=True)
    last_payload_hash = db.Column(db.String(128), nullable=True)
    last_push_reason = db.Column(db.String(128), nullable=True)
    last_counts_json = db.Column(db.Text, nullable=True)


class MirrorSyncMetadataMixin:
    source_updated_at = db.Column(db.DateTime, nullable=True, index=True)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    sync_batch_id = db.Column(db.String(64), nullable=True, index=True)
    row_fingerprint = db.Column(db.String(64), nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)


class ERPSyncBatch(db.Model):
    __tablename__ = 'erp_sync_batches'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    worker_name = db.Column(db.String(128), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='running')
    family = db.Column(db.String(32), nullable=True, index=True)
    table_count = db.Column(db.Integer, nullable=False, default=0)
    rows_extracted = db.Column(db.Integer, nullable=False, default=0)
    rows_staged = db.Column(db.Integer, nullable=False, default=0)
    rows_upserted = db.Column(db.Integer, nullable=False, default=0)
    rows_deleted = db.Column(db.Integer, nullable=False, default=0)
    duration_ms = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)


class ERPSyncTableState(db.Model):
    __tablename__ = 'erp_sync_table_state'
    id = db.Column(db.Integer, primary_key=True)
    table_name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    family = db.Column(db.String(32), nullable=False, index=True)
    strategy = db.Column(db.String(32), nullable=False)
    last_batch_id = db.Column(db.String(64), nullable=True, index=True)
    last_status = db.Column(db.String(32), nullable=False, default='pending')
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    last_source_updated_at = db.Column(db.DateTime, nullable=True)
    last_row_count = db.Column(db.Integer, nullable=False, default=0)
    last_duration_ms = db.Column(db.Integer, nullable=False, default=0)


class ERPMirrorCustomer(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_cust'
    id = db.Column(db.Integer, primary_key=True)
    cust_key = db.Column(db.String(64), nullable=False, index=True)
    cust_code = db.Column(db.String(64), nullable=False, index=True)
    cust_name = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    balance = db.Column(db.Numeric(18, 2), nullable=True)
    credit_limit = db.Column(db.Numeric(18, 2), nullable=True)
    credit_account = db.Column(db.Boolean, nullable=True)
    cust_type = db.Column(db.String(32), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('cust_key', name='uq_erp_mirror_cust_key'),
    )


class ERPMirrorCustomerShipTo(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_cust_shipto'
    id = db.Column(db.Integer, primary_key=True)
    cust_key = db.Column(db.String(64), nullable=False, index=True)
    seq_num = db.Column(db.String(32), nullable=False)
    shipto_name = db.Column(db.String(255), nullable=True)
    address_1 = db.Column(db.String(255), nullable=True)
    address_2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(128), nullable=True)
    state = db.Column(db.String(32), nullable=True)
    zip = db.Column(db.String(32), nullable=True)
    attention = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(64), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('cust_key', 'seq_num', name='uq_erp_mirror_cust_shipto_key'),
    )


class ERPMirrorItem(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_item'
    id = db.Column(db.Integer, primary_key=True)
    item_ptr = db.Column(db.String(64), nullable=False, index=True)
    item = db.Column(db.String(128), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    stocking_uom = db.Column(db.String(32), nullable=True)
    item_group = db.Column(db.String(64), nullable=True)
    product_line = db.Column(db.String(64), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('item_ptr', name='uq_erp_mirror_item_ptr'),
    )


class ERPMirrorItemBranch(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_item_branch'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    item_ptr = db.Column(db.String(64), nullable=False, index=True)
    handling_code = db.Column(db.String(64), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    qty_on_hand = db.Column(db.Numeric(18, 4), nullable=True)
    qty_available = db.Column(db.Numeric(18, 4), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'item_ptr', name='uq_erp_mirror_item_branch_key'),
    )


class ERPMirrorItemUomConv(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_item_uomconv'
    id = db.Column(db.Integer, primary_key=True)
    item_ptr = db.Column(db.String(64), nullable=False, index=True)
    uom_ptr = db.Column(db.String(64), nullable=False)
    conv_factor_from_stocking = db.Column(db.Numeric(18, 6), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('item_ptr', 'uom_ptr', name='uq_erp_mirror_item_uomconv_key'),
    )


class ERPMirrorSalesOrderHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_so_header'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    so_id = db.Column(db.String(64), nullable=False, index=True)
    so_status = db.Column(db.String(16), nullable=True, index=True)
    sale_type = db.Column(db.String(32), nullable=True)
    cust_key = db.Column(db.String(64), nullable=True, index=True)
    shipto_seq_num = db.Column(db.String(32), nullable=True)
    reference = db.Column(db.String(255), nullable=True)
    expect_date = db.Column(db.DateTime, nullable=True)
    created_date = db.Column(db.DateTime, nullable=True)
    invoice_date = db.Column(db.DateTime, nullable=True)
    ship_date = db.Column(db.DateTime, nullable=True)
    promise_date = db.Column(db.DateTime, nullable=True)
    ship_via = db.Column(db.String(128), nullable=True)
    terms = db.Column(db.String(64), nullable=True)
    salesperson = db.Column(db.String(64), nullable=True)
    po_number = db.Column(db.String(128), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'so_id', name='uq_erp_mirror_so_header_key'),
    )


class ERPMirrorSalesOrderLine(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_so_detail'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    so_id = db.Column(db.String(64), nullable=False, index=True)
    sequence = db.Column(db.Integer, nullable=False)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    qty_ordered = db.Column(db.Numeric(18, 4), nullable=True)
    qty_shipped = db.Column(db.Numeric(18, 4), nullable=True)
    backordered_qty = db.Column(db.Numeric(18, 4), nullable=True)
    date_required = db.Column(db.DateTime, nullable=True)
    price = db.Column(db.Numeric(18, 4), nullable=True)
    price_uom_ptr = db.Column(db.String(64), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'so_id', 'sequence', name='uq_erp_mirror_so_detail_key'),
    )


class ERPMirrorShipmentHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_shipments_header'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    so_id = db.Column(db.String(64), nullable=False, index=True)
    shipment_num = db.Column(db.String(64), nullable=False)
    status_flag = db.Column(db.String(16), nullable=True)
    status_flag_delivery = db.Column(db.String(16), nullable=True)
    invoice_date = db.Column(db.DateTime, nullable=True)
    ship_date = db.Column(db.DateTime, nullable=True)
    loaded_date = db.Column(db.DateTime, nullable=True)
    loaded_time = db.Column(db.String(32), nullable=True)
    route_id_char = db.Column(db.String(64), nullable=True)
    ship_via = db.Column(db.String(128), nullable=True)
    driver = db.Column(db.String(128), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'so_id', 'shipment_num', name='uq_erp_mirror_shipments_header_key'),
    )


class ERPMirrorShipmentLine(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_shipments_detail'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    so_id = db.Column(db.String(64), nullable=False, index=True)
    shipment_num = db.Column(db.String(64), nullable=False)
    line_no = db.Column(db.Integer, nullable=False)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    qty = db.Column(db.Numeric(18, 4), nullable=True)
    qty_ordered = db.Column(db.Numeric(18, 4), nullable=True)
    qty_shipped = db.Column(db.Numeric(18, 4), nullable=True)
    price = db.Column(db.Numeric(18, 4), nullable=True)
    price_uom_ptr = db.Column(db.String(64), nullable=True)
    weight = db.Column(db.Numeric(18, 4), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'so_id', 'shipment_num', 'line_no', name='uq_erp_mirror_shipments_detail_key'),
    )


class ERPMirrorWorkOrderHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_wo_header'
    id = db.Column(db.Integer, primary_key=True)
    wo_id = db.Column(db.String(64), nullable=False, index=True)
    source = db.Column(db.String(32), nullable=True)
    source_id = db.Column(db.String(64), nullable=True, index=True)
    source_seq = db.Column(db.Integer, nullable=True)
    wo_status = db.Column(db.String(64), nullable=True, index=True)
    wo_rule = db.Column(db.String(64), nullable=True)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    qty = db.Column(db.Numeric(18, 4), nullable=True)
    department = db.Column(db.String(64), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('wo_id', name='uq_erp_mirror_wo_header_key'),
    )


class ERPMirrorPickHeaderNormalized(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_pick_header'
    id = db.Column(db.Integer, primary_key=True)
    pick_id = db.Column(db.String(64), nullable=False, index=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    created_date = db.Column(db.DateTime, nullable=True)
    created_time = db.Column(db.String(32), nullable=True)
    print_status = db.Column(db.String(64), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('pick_id', 'system_id', name='uq_erp_mirror_pick_header_key'),
    )


class ERPMirrorPickDetailNormalized(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_pick_detail'
    id = db.Column(db.Integer, primary_key=True)
    pick_id = db.Column(db.String(64), nullable=False, index=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    tran_type = db.Column(db.String(32), nullable=False)
    tran_id = db.Column(db.String(64), nullable=False, index=True)
    sequence = db.Column(db.Integer, nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('pick_id', 'system_id', 'tran_type', 'tran_id', 'sequence', name='uq_erp_mirror_pick_detail_key'),
    )


class ERPMirrorArOpen(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_aropen'
    id = db.Column(db.Integer, primary_key=True)
    ref_num = db.Column(db.String(64), nullable=False, index=True)
    cust_key = db.Column(db.String(64), nullable=True, index=True)
    ref_date = db.Column(db.DateTime, nullable=True)
    update_date = db.Column(db.DateTime, nullable=True)
    amount = db.Column(db.Numeric(18, 2), nullable=True)
    open_amt = db.Column(db.Numeric(18, 2), nullable=True)
    ref_type = db.Column(db.String(16), nullable=True)
    shipto_seq = db.Column(db.String(32), nullable=True)
    statement_id = db.Column(db.String(64), nullable=True)
    discount_amt = db.Column(db.Numeric(18, 2), nullable=True)
    discount_taken = db.Column(db.Numeric(18, 2), nullable=True)
    ref_num_sysid = db.Column(db.String(32), nullable=True, index=True)
    paid_in_full_date = db.Column(db.DateTime, nullable=True)
    open_flag = db.Column(db.Boolean, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('ref_num', name='uq_erp_mirror_aropen_key'),
    )


class ERPMirrorArOpenDetail(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_aropendt'
    id = db.Column(db.Integer, primary_key=True)
    ref_num = db.Column(db.String(64), nullable=False, index=True)
    tran_id = db.Column(db.String(64), nullable=True, index=True)
    ref_num_seq = db.Column(db.Integer, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('ref_num', 'tran_id', 'ref_num_seq', name='uq_erp_mirror_aropendt_key'),
    )


class ERPMirrorPrintTransaction(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_print_transaction'
    id = db.Column(db.Integer, primary_key=True)
    tran_id = db.Column(db.String(64), nullable=False, index=True)
    tran_type = db.Column(db.String(64), nullable=False, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('tran_id', 'tran_type', name='uq_erp_mirror_print_transaction_key'),
    )


class ERPMirrorPrintTransactionDetail(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_print_transaction_detail'
    id = db.Column(db.Integer, primary_key=True)
    tran_id = db.Column(db.String(64), nullable=False, index=True)
    printer_id = db.Column(db.String(64), nullable=True)
    printer_destination = db.Column(db.String(255), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('tran_id', 'printer_id', 'printer_destination', name='uq_erp_mirror_print_transaction_detail_key'),
    )

# -------------------------------------------------------------------
# Sales Team — Customer Notes / Call Log
# -------------------------------------------------------------------

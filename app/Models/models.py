import uuid as _uuid

from app.extensions import db
from datetime import datetime  # If you're using datetime for the DateTime columns


class Pickster(db.Model):
    __tablename__ = 'pickster'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    user_type = db.Column(db.String(50), default='picker') # 'picker', 'door_builder', etc.
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    picks = db.relationship('Pick', backref='pickster', lazy=True)
    # 'picks' establishes a relationship to the Pick model, with a back-reference to 'pickster'
    # 'lazy=True' specifies that the related objects are loaded as necessary

class Pick(db.Model):
    __tablename__ = 'pick'
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_time = db.Column(db.DateTime, index=True)
    barcode_number = db.Column(db.String(120), nullable=False)
    shipment_num = db.Column(db.String(64), nullable=True)
    picker_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=False)
    pick_type_id = db.Column(db.Integer, db.ForeignKey('PickTypes.pick_type_id'))
    notes = db.Column(db.Text)
    branch_code = db.Column(db.String(32), nullable=True, index=True)

class PickTypes(db.Model):
    __tablename__ = 'PickTypes'
    pick_type_id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(128),unique=True, nullable=False)


class WorkOrder(db.Model):
    """Read-only ERP mirror of dbo.wo_header, synced every ~10 minutes."""
    __tablename__ = 'erp_mirror_wo_header'
    id = db.Column(db.Integer, primary_key=True)
    wo_id = db.Column(db.String(64), nullable=False, index=True)
    source = db.Column(db.String(32), nullable=True)
    source_id = db.Column(db.String(64), nullable=True, index=True)  # Sales Order number
    source_seq = db.Column(db.Integer, nullable=True)
    wo_status = db.Column(db.String(64), nullable=True, index=True)
    wo_rule = db.Column(db.String(64), nullable=True)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    qty = db.Column(db.Numeric(18, 4), nullable=True)
    department = db.Column(db.String(64), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    # Mirror metadata columns
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    synced_at = db.Column(db.DateTime, nullable=True)
    source_updated_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('wo_id', name='uq_erp_mirror_wo_header_key'),
    )


class WorkOrderAssignment(db.Model):
    """Local assignment/tracking record linking an ERP work order to a builder."""
    __tablename__ = 'wo_assignments'
    id = db.Column(db.Integer, primary_key=True)
    wo_id = db.Column(db.String(128), nullable=False, unique=True, index=True)
    sales_order_number = db.Column(db.String(128))
    item_number = db.Column(db.String(128))
    description = db.Column(db.String(256))
    status = db.Column(db.String(50), default='Open')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('pickster.id'))
    completed_by_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    branch_code = db.Column(db.String(32), nullable=True, index=True)

    assigned_to = db.relationship('Pickster', foreign_keys=[assigned_to_id], backref=db.backref('wo_assignments', lazy=True))
    completed_by = db.relationship('Pickster', foreign_keys=[completed_by_id], backref=db.backref('completed_wo_assignments', lazy=True))

    @property
    def work_order_number(self):
        """Alias for wo_id — used by templates that predate the erp_mirror migration."""
        return self.wo_id


class PickAssignment(db.Model):
    __tablename__ = 'pick_assignments'
    id = db.Column(db.Integer, primary_key=True)
    so_number = db.Column(db.String(50), nullable=False) # Sales Order Number
    handling_code = db.Column(db.String(50), nullable=True) # Optional: Assign per code?
    picker_id = db.Column(db.Integer, db.ForeignKey('pickster.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    branch_code = db.Column(db.String(32), nullable=True, index=True)

    picker = db.relationship('Pickster', backref=db.backref('assignments', lazy=True))



# -------------------------------------------------------------------
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
    actor = db.relationship('Pickster', backref=db.backref('audit_events', lazy=True))
    notes = db.Column(db.Text)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class AppUser(db.Model):
    """Authenticated application user. One record per person who can log in."""
    __tablename__ = 'app_users'

    id = db.Column(db.Integer, primary_key=True)
    # Login identity
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    # Rep / employee ID that ties this login to ERP data (e.g. "mschmit")
    user_id = db.Column(db.String(64), nullable=True, index=True)
    display_name = db.Column(db.String(128), nullable=True)
    # Phase 2: phone for SMS OTP — stored E.164 format, e.g. "+16025551234"
    phone = db.Column(db.String(32), nullable=True)
    # JSON array of role strings e.g. ["sales", "ops"]
    roles = db.Column(db.JSON, nullable=False, default=list)
    # Home branch code e.g. "20GR" — used for PO module scoping. NULL = all branches.
    branch = db.Column(db.String(16), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def has_role(self, *roles):
        """Return True if user holds any of the requested roles or is admin."""
        user_roles = set(self.roles or [])
        return 'admin' in user_roles or bool(user_roles & set(roles))

    def __repr__(self):
        return f'<AppUser {self.email}>'


class POSubmission(db.Model):
    """PO check-in submission — records a warehouse worker photographing received goods."""
    __tablename__ = 'po_submissions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    po_number = db.Column(db.Text, nullable=False)
    image_urls = db.Column(db.JSON, nullable=False, default=list)
    supplier_name = db.Column(db.Text, nullable=True)
    supplier_key = db.Column(db.Text, nullable=True)
    po_status = db.Column(db.Text, nullable=True)     # ERP status at submission time
    submission_type = db.Column(db.String(32), nullable=False, default='receiving_checkin')
    priority = db.Column(db.String(16), nullable=True)
    queue_item_id = db.Column(db.Integer, db.ForeignKey('purchasing_work_queue.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending/reviewed/flagged
    submitted_by = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    submitted_username = db.Column(db.Text, nullable=True)  # denormalized — name at submit time
    branch = db.Column(db.Text, nullable=True)              # denormalized from AppUser.branch
    reviewer_notes = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    submitter = db.relationship('AppUser', foreign_keys=[submitted_by],
                                backref=db.backref('po_submissions_submitted', lazy=True))
    reviewer_user = db.relationship('AppUser', foreign_keys=[reviewed_by],
                                    backref=db.backref('po_submissions_reviewed', lazy=True))
    queue_item = db.relationship('PurchasingWorkQueue', foreign_keys=[queue_item_id], backref=db.backref('linked_submissions', lazy=True))

    def __repr__(self):
        return f'<POSubmission {self.id} PO={self.po_number} status={self.status}>'


class OTPCode(db.Model):
    """Short-lived one-time passcode sent to a user's email (or phone in phase 2)."""
    __tablename__ = 'otp_codes'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    code = db.Column(db.String(8), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False, index=True)

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
    lat = db.Column(db.Numeric(9, 6), nullable=True)
    lon = db.Column(db.Numeric(9, 6), nullable=True)
    geocoded_at = db.Column(db.DateTime, nullable=True)
    geocode_source = db.Column(db.String(64), nullable=True)
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
    order_writer = db.Column(db.String(64), nullable=True)
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

# -------------------------------------------------------------------
# File Storage — Polymorphic file attachments backed by R2
# Files can be attached to any entity type (rma, bid, takeoff, job, etc.)
# -------------------------------------------------------------------

class File(db.Model):
    __tablename__ = 'files'
    id                = db.Column(db.Integer, primary_key=True)
    entity_type       = db.Column(db.String(50), nullable=False, index=True)   # 'rma', 'bid', 'takeoff', 'job'
    entity_id         = db.Column(db.String(100), nullable=False, index=True)  # e.g. RMA number, bid ID
    category          = db.Column(db.String(50))                               # 'plan', 'markup', 'quote', 'photo', 'receipt'
    original_filename = db.Column(db.String(512), nullable=False)
    object_key        = db.Column(db.String(1024), nullable=False)             # R2 bucket key
    mime_type         = db.Column(db.String(128))
    size_bytes        = db.Column(db.BigInteger)
    uploaded_by       = db.Column(db.String(128))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted        = db.Column(db.Boolean, default=False, index=True)

    versions = db.relationship('FileVersion', backref='file', lazy='dynamic',
                               order_by='FileVersion.version_number.desc()')


class FileVersion(db.Model):
    __tablename__ = 'file_versions'
    id              = db.Column(db.Integer, primary_key=True)
    file_id         = db.Column(db.Integer, db.ForeignKey('files.id'), nullable=False, index=True)
    version_number  = db.Column(db.Integer, nullable=False, default=1)
    object_key      = db.Column(db.String(1024), nullable=False)
    size_bytes      = db.Column(db.BigInteger)
    change_note     = db.Column(db.String(512))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    created_by      = db.Column(db.String(128))


# -------------------------------------------------------------------
# Pre-computed Dashboard Stats (updated by Pi sync worker)
# -------------------------------------------------------------------

class DashboardStats(db.Model):
    """Per-branch row holding pre-computed dashboard counts.

    One row per branch (system_id).  Updated by the Pi sync worker each cycle
    so the dashboard reads are a single SELECT instead of multi-join ERP queries.
    """
    __tablename__ = 'dashboard_stats'
    system_id = db.Column(db.String(32), primary_key=True)  # e.g. '20GR', '25BW'
    open_picks = db.Column(db.Integer, nullable=False, default=0)
    handling_breakdown_json = db.Column(db.Text, nullable=True)   # JSON dict {code: count}
    open_work_orders = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# -------------------------------------------------------------------
# Purchasing module
# -------------------------------------------------------------------

class _PurchasingSystemIdCompatibilityMixin:
    """Temporary compatibility alias while app-owned purchasing code moves off branch_code."""

    @property
    def branch_code(self):
        return self.system_id

    @branch_code.setter
    def branch_code(self, value):
        self.system_id = value

class ERPMirrorPurchaseOrderHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_po_header'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    po_id = db.Column(db.String(64), nullable=True, index=True)
    po_number = db.Column(db.String(64), nullable=False, index=True)
    supplier_key = db.Column(db.String(64), nullable=True, index=True)
    supplier_code = db.Column(db.String(64), nullable=True)
    supplier_name = db.Column(db.String(255), nullable=True)
    ship_from_seq = db.Column(db.String(32), nullable=True)
    po_status = db.Column(db.String(32), nullable=True, index=True)
    purchase_type_code = db.Column(db.String(32), nullable=True)
    buyer_id = db.Column(db.String(64), nullable=True, index=True)
    reference = db.Column(db.String(255), nullable=True)
    order_date = db.Column(db.DateTime, nullable=True)
    expect_ship_date = db.Column(db.DateTime, nullable=True)
    expect_date = db.Column(db.DateTime, nullable=True)
    ship_via = db.Column(db.String(128), nullable=True)
    freight_terms = db.Column(db.String(128), nullable=True)
    payment_terms = db.Column(db.String(128), nullable=True)
    currency_code = db.Column(db.String(32), nullable=True)
    total_amount = db.Column(db.Numeric(18, 2), nullable=True)
    open_amount = db.Column(db.Numeric(18, 2), nullable=True)
    finalized_status = db.Column(db.String(32), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'po_number', name='uq_erp_mirror_po_header_key'),
    )


class ERPMirrorPurchaseOrderDetail(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_po_detail'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=False, index=True)
    line_number = db.Column(db.Integer, nullable=False)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    item_code = db.Column(db.String(128), nullable=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    supplier_part_number = db.Column(db.String(128), nullable=True)
    qty_ordered = db.Column(db.Numeric(18, 4), nullable=True)
    qty_received = db.Column(db.Numeric(18, 4), nullable=True)
    qty_open = db.Column(db.Numeric(18, 4), nullable=True)
    unit_cost = db.Column(db.Numeric(18, 4), nullable=True)
    extended_cost = db.Column(db.Numeric(18, 4), nullable=True)
    line_status = db.Column(db.String(32), nullable=True, index=True)
    expected_ship_date = db.Column(db.DateTime, nullable=True)
    expected_receipt_date = db.Column(db.DateTime, nullable=True)
    linked_so_number = db.Column(db.String(64), nullable=True, index=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'po_number', 'line_number', name='uq_erp_mirror_po_detail_key'),
    )


class ERPMirrorReceivingHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_receiving_header'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=False, index=True)
    receiving_number = db.Column(db.String(64), nullable=False, index=True)
    session_status = db.Column(db.String(32), nullable=True, index=True)
    received_at = db.Column(db.DateTime, nullable=True)
    received_by = db.Column(db.String(64), nullable=True)
    supplier_invoice_number = db.Column(db.String(128), nullable=True)
    total_cost = db.Column(db.Numeric(18, 2), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'po_number', 'receiving_number', name='uq_erp_mirror_receiving_header_key'),
    )


class ERPMirrorReceivingDetail(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_receiving_detail'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=False, index=True)
    receiving_number = db.Column(db.String(64), nullable=False, index=True)
    line_number = db.Column(db.Integer, nullable=False)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    qty_received = db.Column(db.Numeric(18, 4), nullable=True)
    unit_cost = db.Column(db.Numeric(18, 4), nullable=True)
    line_status = db.Column(db.String(32), nullable=True, index=True)
    variance_amount = db.Column(db.Numeric(18, 4), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'po_number', 'receiving_number', 'line_number', name='uq_erp_mirror_receiving_detail_key'),
    )


class ERPMirrorReceivingStatus(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_receiving_status'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=False, index=True)
    receiving_number = db.Column(db.String(64), nullable=True, index=True)
    status_code = db.Column(db.String(32), nullable=True, index=True)
    status_description = db.Column(db.String(255), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'po_number', 'receiving_number', 'status_code', name='uq_erp_mirror_receiving_status_key'),
    )


class ERPMirrorSuggestedPOHeader(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_ppo_header'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    suggestion_number = db.Column(db.String(64), nullable=False, index=True)
    supplier_key = db.Column(db.String(64), nullable=True, index=True)
    supplier_name = db.Column(db.String(255), nullable=True)
    buyer_id = db.Column(db.String(64), nullable=True, index=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=True, index=True)
    total_amount = db.Column(db.Numeric(18, 2), nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'suggestion_number', name='uq_erp_mirror_ppo_header_key'),
    )


class ERPMirrorSuggestedPODetail(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_ppo_detail'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    suggestion_number = db.Column(db.String(64), nullable=False, index=True)
    line_number = db.Column(db.Integer, nullable=False)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    item_code = db.Column(db.String(128), nullable=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    recommended_qty = db.Column(db.Numeric(18, 4), nullable=True)
    reorder_point = db.Column(db.Numeric(18, 4), nullable=True)
    net_qty = db.Column(db.Numeric(18, 4), nullable=True)
    projected_usage = db.Column(db.Numeric(18, 4), nullable=True)
    abc_class = db.Column(db.String(8), nullable=True, index=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('system_id', 'suggestion_number', 'line_number', name='uq_erp_mirror_ppo_detail_key'),
    )


class ERPMirrorItemSupplier(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_item_supplier'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    item_ptr = db.Column(db.String(64), nullable=False, index=True)
    supplier_key = db.Column(db.String(64), nullable=False, index=True)
    supplier_code = db.Column(db.String(64), nullable=True)
    supplier_name = db.Column(db.String(255), nullable=True)
    supplier_part_number = db.Column(db.String(128), nullable=True)
    lead_days = db.Column(db.Integer, nullable=True)
    min_order_qty = db.Column(db.Numeric(18, 4), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    # Unique on (COALESCE(system_id,''), item_ptr, supplier_key) — enforced via
    # functional index in migration s2t3u4v5w6x7 (not a SQLAlchemy UniqueConstraint
    # because SQLAlchemy can't express COALESCE in a constraint).
    __table_args__ = ()


class ERPMirrorSupplier(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_supplier_dim'
    id = db.Column(db.Integer, primary_key=True)
    supplier_key = db.Column(db.String(64), nullable=False, index=True)
    supplier_code = db.Column(db.String(64), nullable=True, index=True)
    supplier_name = db.Column(db.String(255), nullable=True, index=True)
    buyer_id = db.Column(db.String(64), nullable=True, index=True)
    phone = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=True)
    branch_code = db.Column(db.String(32), nullable=True, index=True)
    __table_args__ = (
        db.UniqueConstraint('supplier_key', name='uq_erp_mirror_supplier_dim_key'),
    )


class ERPMirrorPurchaseType(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_purchase_type'
    id = db.Column(db.Integer, primary_key=True)
    purchase_type_code = db.Column(db.String(32), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    affects_inventory = db.Column(db.Boolean, nullable=True)
    is_expense_type = db.Column(db.Boolean, nullable=True)
    is_transfer_type = db.Column(db.Boolean, nullable=True)
    default_for_stock_suggested = db.Column(db.Boolean, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('purchase_type_code', name='uq_erp_mirror_purchase_type_key'),
    )


class ERPMirrorPurchaseCost(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_purchase_costs'
    id = db.Column(db.Integer, primary_key=True)
    cost_type_code = db.Column(db.String(64), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    allocation_method = db.Column(db.String(64), nullable=True)
    available_for_use = db.Column(db.Boolean, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('cost_type_code', name='uq_erp_mirror_purchase_costs_key'),
    )


class ERPMirrorPurchasingParameter(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_param_po'
    id = db.Column(db.Integer, primary_key=True)
    branch_code = db.Column(db.String(32), nullable=False, index=True)
    use_finalize_process = db.Column(db.Boolean, nullable=True)
    recalc_after_detail_update = db.Column(db.String(32), nullable=True)
    include_credit_hold_backorders = db.Column(db.Boolean, nullable=True)
    limit_trend_percentage = db.Column(db.Numeric(10, 4), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('branch_code', name='uq_erp_mirror_param_po_key'),
    )


class ERPMirrorPurchasingCostParameter(db.Model, MirrorSyncMetadataMixin):
    __tablename__ = 'erp_mirror_param_po_cost'
    id = db.Column(db.Integer, primary_key=True)
    branch_code = db.Column(db.String(32), nullable=False, index=True)
    cost_type_code = db.Column(db.String(64), nullable=False, index=True)
    default_supplier_key = db.Column(db.String(64), nullable=True, index=True)
    allocation_method = db.Column(db.String(64), nullable=True)
    __table_args__ = (
        db.UniqueConstraint('branch_code', 'cost_type_code', name='uq_erp_mirror_param_po_cost_key'),
    )


class PurchasingAssignment(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_assignments'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.String(32), nullable=False, index=True)
    buyer_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True, index=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    assignment_type = db.Column(db.String(32), nullable=False, default='branch')
    supplier_key = db.Column(db.String(64), nullable=True, index=True)
    item_ptr = db.Column(db.String(64), nullable=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buyer = db.relationship('AppUser', foreign_keys=[buyer_user_id], backref=db.backref('purchasing_assignments', lazy=True))
    assigned_by = db.relationship('AppUser', foreign_keys=[assigned_by_user_id], backref=db.backref('purchasing_assignments_created', lazy=True))


class PurchasingWorkQueue(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_work_queue'
    id = db.Column(db.Integer, primary_key=True)
    queue_type = db.Column(db.String(32), nullable=False, index=True)
    reference_type = db.Column(db.String(32), nullable=False, index=True)
    reference_number = db.Column(db.String(128), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    buyer_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True, index=True)
    supplier_key = db.Column(db.String(64), nullable=True, index=True)
    supplier_name = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='open', index=True)
    priority = db.Column(db.String(16), nullable=False, default='medium', index=True)
    severity = db.Column(db.String(16), nullable=True, index=True)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buyer = db.relationship('AppUser', foreign_keys=[buyer_user_id], backref=db.backref('purchasing_queue_items', lazy=True))
    created_by = db.relationship('AppUser', foreign_keys=[created_by_user_id], backref=db.backref('purchasing_queue_created', lazy=True))
    resolved_by = db.relationship('AppUser', foreign_keys=[resolved_by_user_id], backref=db.backref('purchasing_queue_resolved', lazy=True))


class PurchasingNote(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_notes'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.String(128), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    body = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, nullable=False, default=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    created_by = db.relationship('AppUser', backref=db.backref('purchasing_notes', lazy=True))


class PurchasingTask(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    queue_item_id = db.Column(db.Integer, db.ForeignKey('purchasing_work_queue.id', ondelete='SET NULL'), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    assignee_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(32), nullable=False, default='open', index=True)
    priority = db.Column(db.String(16), nullable=False, default='medium', index=True)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    queue_item = db.relationship('PurchasingWorkQueue', backref=db.backref('tasks', lazy=True))
    assignee = db.relationship('AppUser', foreign_keys=[assignee_user_id], backref=db.backref('purchasing_tasks', lazy=True))
    created_by = db.relationship('AppUser', foreign_keys=[created_by_user_id], backref=db.backref('purchasing_tasks_created', lazy=True))


class PurchasingApproval(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_approvals'
    id = db.Column(db.Integer, primary_key=True)
    approval_type = db.Column(db.String(32), nullable=False, index=True)
    entity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.String(128), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    approver_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending', index=True)
    reason = db.Column(db.Text, nullable=True)
    decision_notes = db.Column(db.Text, nullable=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    decided_at = db.Column(db.DateTime, nullable=True)

    requested_by = db.relationship('AppUser', foreign_keys=[requested_by_user_id], backref=db.backref('purchasing_approvals_requested', lazy=True))
    approver = db.relationship('AppUser', foreign_keys=[approver_user_id], backref=db.backref('purchasing_approvals', lazy=True))


class PurchasingExceptionEvent(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_exception_events'
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    event_status = db.Column(db.String(32), nullable=False, default='open', index=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    receiving_number = db.Column(db.String(64), nullable=True, index=True)
    queue_item_id = db.Column(db.Integer, db.ForeignKey('purchasing_work_queue.id', ondelete='SET NULL'), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    supplier_key = db.Column(db.String(64), nullable=True, index=True)
    severity = db.Column(db.String(16), nullable=False, default='medium', index=True)
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    queue_item = db.relationship('PurchasingWorkQueue', backref=db.backref('exceptions', lazy=True))
    created_by = db.relationship('AppUser', foreign_keys=[created_by_user_id], backref=db.backref('purchasing_exceptions_created', lazy=True))
    resolved_by = db.relationship('AppUser', foreign_keys=[resolved_by_user_id], backref=db.backref('purchasing_exceptions_resolved', lazy=True))


class PurchasingDashboardSnapshot(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_dashboard_snapshots'
    id = db.Column(db.Integer, primary_key=True)
    snapshot_type = db.Column(db.String(32), nullable=False, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    buyer_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True, index=True)
    payload = db.Column(db.JSON, nullable=False)
    captured_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    buyer = db.relationship('AppUser', backref=db.backref('purchasing_dashboard_snapshots', lazy=True))


class PurchasingActivity(db.Model, _PurchasingSystemIdCompatibilityMixin):
    __tablename__ = 'purchasing_activity'
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.String(128), nullable=False, index=True)
    po_number = db.Column(db.String(64), nullable=True, index=True)
    system_id = db.Column(db.String(32), nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('app_users.id', ondelete='SET NULL'), nullable=True, index=True)
    summary = db.Column(db.String(255), nullable=False)
    before_state = db.Column(db.JSON, nullable=True)
    after_state = db.Column(db.JSON, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    actor = db.relationship('AppUser', backref=db.backref('purchasing_activity', lazy=True))

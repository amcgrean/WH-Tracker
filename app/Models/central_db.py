from app.extensions import db

# -------------------------------------------------------------------
# Central Database Models (Bound to 'central_db')
# These models map to the tables synced by the beisser-api PostgreSQL
# repository for creating a centralized data source.
# -------------------------------------------------------------------

class CentralSalesOrder(db.Model):
    __bind_key__ = 'central_db'
    __tablename__ = 'sales_orders'
    
    prowid = db.Column(db.String(255), primary_key=True)
    so_id = db.Column(db.String(50), index=True)
    system_id = db.Column(db.String(50))
    so_status = db.Column(db.String(10))
    customer_key = db.Column(db.String(100))
    cust_name = db.Column(db.String(255))
    address_1 = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(50))
    reference = db.Column(db.String(255))
    expect_date = db.Column(db.Date)
    sale_type = db.Column(db.String(50))
    created_date = db.Column(db.Date)
    updated_at = db.Column(db.DateTime)

class CentralSalesOrderLine(db.Model):
    __bind_key__ = 'central_db'
    __tablename__ = 'sales_order_lines'
    
    prowid = db.Column(db.String(255), primary_key=True)
    so_id = db.Column(db.String(50), index=True)
    system_id = db.Column(db.String(50))
    sequence = db.Column(db.Integer)
    item_ptr = db.Column(db.String(100))
    item = db.Column(db.String(100))
    description = db.Column(db.String(255))
    qty_ordered = db.Column(db.Numeric(10, 2))
    cost = db.Column(db.Numeric(10, 2))
    price = db.Column(db.Numeric(10, 2))
    handling_code = db.Column(db.String(50))
    bo = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime)

class CentralInventory(db.Model):
    __bind_key__ = 'central_db'
    __tablename__ = 'inventory'
    
    prowid = db.Column(db.String(255), primary_key=True)
    item = db.Column(db.String(100), index=True)
    description = db.Column(db.String(255))
    system_id = db.Column(db.String(50))
    qty_on_hand = db.Column(db.Numeric(10, 2))
    qty_committed = db.Column(db.Numeric(10, 2))
    qty_available = db.Column(db.Numeric(10, 2))
    branch = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime)

class CentralCustomer(db.Model):
    __bind_key__ = 'central_db'
    __tablename__ = 'customers'
    
    prowid = db.Column(db.String(255), primary_key=True)
    cust_key = db.Column(db.String(100), index=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(255))
    balance = db.Column(db.Numeric(12, 2))
    credit_limit = db.Column(db.Numeric(12, 2))
    updated_at = db.Column(db.DateTime)

class CentralDispatchOrder(db.Model):
    __bind_key__ = 'central_db'
    __tablename__ = 'dispatch_orders'
    
    prowid = db.Column(db.String(255), primary_key=True)
    so_id = db.Column(db.String(50), index=True)
    system_id = db.Column(db.String(50))
    ship_date = db.Column(db.Date)
    status_flag = db.Column(db.String(10))
    driver = db.Column(db.String(100))
    ship_via = db.Column(db.String(100))
    route_id_char = db.Column(db.String(50))
    loaded_date = db.Column(db.Date)
    loaded_time = db.Column(db.String(20))
    status_flag_delivery = db.Column(db.String(10))
    updated_at = db.Column(db.DateTime)

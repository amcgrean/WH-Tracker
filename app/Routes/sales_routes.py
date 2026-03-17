"""
Sales Team Routes
=================
All routes for the Sales hub and its 10 key features.

Feature list:
  1.  Customer 360 Profile        /sales/customer/<customer_number>
  2.  Order History Browser        /sales/orders
  3.  Invoice Lookup               /sales/invoices
  4.  Customer Awards & Loyalty    /sales/awards
  5.  Sales Rep Dashboard          /sales/rep-dashboard
  6.  Quick Order Status Lookup    /sales/order-status
  7.  Customer Notes & Call Log    /sales/customers/<customer_number>/notes
  8.  Product Pricing Reference    /sales/products
  9.  Sales Analytics & Reports    /sales/reports
  10. Customer Statement / AR      /sales/customers/<customer_number>/statement

Data strategy notes
-------------------
* All data is read from the central DB mirror (erp_mirror_picks) plus the new
  tables added in this branch.  No direct ERP connection is required in cloud
  mode — the existing sync endpoint pushes the records we need.
* Historical / invoiced orders will be included once the central DB starts
  receiving them (currently the mirror only holds open orders).  The templates
  and routes are already designed to handle both open and closed statuses so
  the upgrade is additive.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from app.extensions import db
from app.Models.models import ERPMirrorPick, CustomerNote
from datetime import datetime, timedelta
from sqlalchemy import func, distinct, desc, asc

sales = Blueprint('sales', __name__, url_prefix='/sales')

# ---------------------------------------------------------------------------
# Helper: branch display names
# ---------------------------------------------------------------------------
BRANCH_LABELS = {
    '20gr': 'Grimes (20GR)',
    '25bw': 'Birchwood (25BW)',
    '10fd': 'Fort Dodge (10FD)',
    '40cv': 'Coralville (40CV)',
}

ORDER_STATUSES = ['Open', 'Invoiced', 'Closed', 'Cancelled', 'On Hold']


# ---------------------------------------------------------------------------
# 0. Sales Hub — landing page
# ---------------------------------------------------------------------------
@sales.route('/')
def hub():
    """Sales team landing page with quick-access tiles for all 10 features."""
    # Quick KPI counts pulled from the mirror table
    open_orders_count = ERPMirrorPick.query.filter(
        ERPMirrorPick.so_status == 'O'
    ).with_entities(distinct(ERPMirrorPick.so_number)).count()

    total_orders_today = ERPMirrorPick.query.filter(
        ERPMirrorPick.expect_date == datetime.today().strftime('%Y-%m-%d')
    ).with_entities(distinct(ERPMirrorPick.so_number)).count()

    recent_notes = CustomerNote.query.order_by(desc(CustomerNote.created_at)).limit(5).all()

    return render_template(
        'sales/hub.html',
        open_orders_count=open_orders_count,
        total_orders_today=total_orders_today,
        recent_notes=recent_notes,
    )


# ---------------------------------------------------------------------------
# 1. Customer 360 Profile
# ---------------------------------------------------------------------------
@sales.route('/customer/<customer_number>')
def customer_profile(customer_number):
    """Full customer card: contact info, orders, awards, AR snapshot."""
    # Gather all SO rows for this customer from the mirror
    customer_rows = ERPMirrorPick.query.filter(
        ERPMirrorPick.customer_name.ilike(f'%{customer_number}%')
        | (ERPMirrorPick.so_number.ilike(f'%{customer_number}%'))
    ).order_by(desc(ERPMirrorPick.synced_at)).all()

    # Distinct SO numbers for order count
    order_numbers = list({r.so_number for r in customer_rows})
    customer_name = customer_rows[0].customer_name if customer_rows else customer_number

    # Recent notes
    notes = CustomerNote.query.filter_by(
        customer_number=customer_number
    ).order_by(desc(CustomerNote.created_at)).limit(10).all()

    return render_template(
        'sales/customer_profile.html',
        customer_number=customer_number,
        customer_name=customer_name,
        customer_rows=customer_rows,
        order_numbers=order_numbers,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 2. Order History Browser (open + invoiced + historical)
# ---------------------------------------------------------------------------
@sales.route('/orders')
def order_history():
    """Search and browse all orders — open, invoiced, and historical."""
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    branch_filter = request.args.get('branch', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = ERPMirrorPick.query

    if q:
        query = query.filter(
            ERPMirrorPick.so_number.ilike(f'%{q}%')
            | ERPMirrorPick.customer_name.ilike(f'%{q}%')
            | ERPMirrorPick.reference.ilike(f'%{q}%')
        )
    if status_filter:
        query = query.filter(ERPMirrorPick.so_status == status_filter)
    if date_from:
        query = query.filter(ERPMirrorPick.expect_date >= date_from)
    if date_to:
        query = query.filter(ERPMirrorPick.expect_date <= date_to)

    # Collapse to SO-level rows (one row per SO, latest synced)
    subq = (
        db.session.query(
            ERPMirrorPick.so_number,
            func.max(ERPMirrorPick.synced_at).label('latest')
        )
        .group_by(ERPMirrorPick.so_number)
        .subquery()
    )
    query = query.join(
        subq,
        (ERPMirrorPick.so_number == subq.c.so_number)
        & (ERPMirrorPick.synced_at == subq.c.latest)
    ).order_by(desc(ERPMirrorPick.synced_at))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'sales/order_history.html',
        orders=pagination.items,
        pagination=pagination,
        q=q,
        status_filter=status_filter,
        branch_filter=branch_filter,
        date_from=date_from,
        date_to=date_to,
        branch_labels=BRANCH_LABELS,
        order_statuses=ORDER_STATUSES,
    )


# ---------------------------------------------------------------------------
# 3. Invoice Lookup
# ---------------------------------------------------------------------------
@sales.route('/invoices')
def invoice_lookup():
    """Search invoiced orders by invoice/SO number, customer, or date range."""
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)

    # Invoiced = so_status 'I' (placeholder — actual code depends on Agility values)
    query = ERPMirrorPick.query.filter(ERPMirrorPick.so_status.in_(['I', 'C']))

    if q:
        query = query.filter(
            ERPMirrorPick.so_number.ilike(f'%{q}%')
            | ERPMirrorPick.customer_name.ilike(f'%{q}%')
        )
    if date_from:
        query = query.filter(ERPMirrorPick.expect_date >= date_from)
    if date_to:
        query = query.filter(ERPMirrorPick.expect_date <= date_to)

    query = query.order_by(desc(ERPMirrorPick.synced_at))
    pagination = query.paginate(page=page, per_page=50, error_out=False)

    return render_template(
        'sales/invoice_lookup.html',
        invoices=pagination.items,
        pagination=pagination,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# 4. Customer Awards & Loyalty
# ---------------------------------------------------------------------------
@sales.route('/awards')
def awards():
    """View customer award tiers and loyalty standing pulled from central DB."""
    q = request.args.get('q', '').strip()

    # Placeholder: awards data will come from the central DB once synced.
    # For now we surface distinct customers with order counts as a proxy.
    customer_query = db.session.query(
        ERPMirrorPick.customer_name,
        func.count(distinct(ERPMirrorPick.so_number)).label('order_count'),
    ).group_by(ERPMirrorPick.customer_name)

    if q:
        customer_query = customer_query.filter(
            ERPMirrorPick.customer_name.ilike(f'%{q}%')
        )

    customers = customer_query.order_by(desc('order_count')).limit(100).all()

    return render_template(
        'sales/awards.html',
        customers=customers,
        q=q,
    )


# ---------------------------------------------------------------------------
# 5. Sales Rep Dashboard
# ---------------------------------------------------------------------------
@sales.route('/rep-dashboard')
def rep_dashboard():
    """Personal KPIs for a sales rep: volume, order count, trends."""
    rep_name = request.args.get('rep', '').strip()
    period_days = request.args.get('period', 30, type=int)

    since = datetime.utcnow() - timedelta(days=period_days)

    # Aggregate open orders and recent activity from mirror
    branch_counts = db.session.query(
        ERPMirrorPick.handling_code,
        func.count(distinct(ERPMirrorPick.so_number)).label('order_count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.handling_code).all()

    status_breakdown = db.session.query(
        ERPMirrorPick.so_status,
        func.count(distinct(ERPMirrorPick.so_number)).label('count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.so_status).all()

    # Top customers by order count in period
    top_customers = db.session.query(
        ERPMirrorPick.customer_name,
        func.count(distinct(ERPMirrorPick.so_number)).label('order_count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.customer_name).order_by(
        desc('order_count')
    ).limit(10).all()

    return render_template(
        'sales/rep_dashboard.html',
        rep_name=rep_name,
        period_days=period_days,
        branch_counts=branch_counts,
        status_breakdown=status_breakdown,
        top_customers=top_customers,
    )


# ---------------------------------------------------------------------------
# 6. Quick Order Status Lookup
# ---------------------------------------------------------------------------
@sales.route('/order-status')
def order_status():
    """Fast SO / customer lookup for reps on a call."""
    q = request.args.get('q', '').strip()
    results = []
    if q:
        results = ERPMirrorPick.query.filter(
            ERPMirrorPick.so_number.ilike(f'%{q}%')
            | ERPMirrorPick.customer_name.ilike(f'%{q}%')
        ).order_by(desc(ERPMirrorPick.synced_at)).limit(30).all()

    return render_template(
        'sales/order_status.html',
        q=q,
        results=results,
    )


# API endpoint for instant search suggestions
@sales.route('/api/order-status-search')
def order_status_search_api():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    rows = ERPMirrorPick.query.filter(
        ERPMirrorPick.so_number.ilike(f'%{q}%')
        | ERPMirrorPick.customer_name.ilike(f'%{q}%')
    ).with_entities(
        ERPMirrorPick.so_number,
        ERPMirrorPick.customer_name,
        ERPMirrorPick.so_status,
        ERPMirrorPick.expect_date,
        ERPMirrorPick.handling_code,
    ).distinct(ERPMirrorPick.so_number).limit(10).all()
    return jsonify([
        {
            'so_number': r.so_number,
            'customer_name': r.customer_name,
            'so_status': r.so_status,
            'expect_date': r.expect_date,
            'handling_code': r.handling_code,
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# 7. Customer Notes & Call Log
# ---------------------------------------------------------------------------
@sales.route('/customers/<customer_number>/notes', methods=['GET', 'POST'])
def customer_notes(customer_number):
    """Log and view calls, site visits, emails for a customer."""
    if request.method == 'POST':
        note_type = request.form.get('note_type', 'Call')
        body = request.form.get('body', '').strip()
        rep_name = request.form.get('rep_name', '').strip()
        if body:
            note = CustomerNote(
                customer_number=customer_number,
                note_type=note_type,
                body=body,
                rep_name=rep_name,
                created_at=datetime.utcnow(),
            )
            db.session.add(note)
            db.session.commit()
            flash('Note saved.', 'success')
        return redirect(url_for('sales.customer_notes', customer_number=customer_number))

    notes = CustomerNote.query.filter_by(
        customer_number=customer_number
    ).order_by(desc(CustomerNote.created_at)).all()

    customer_row = ERPMirrorPick.query.filter(
        ERPMirrorPick.so_number.ilike(f'%{customer_number}%')
        | ERPMirrorPick.customer_name.ilike(f'%{customer_number}%')
    ).first()
    customer_name = customer_row.customer_name if customer_row else customer_number

    return render_template(
        'sales/customer_notes.html',
        customer_number=customer_number,
        customer_name=customer_name,
        notes=notes,
        note_types=['Call', 'Visit', 'Email', 'Quote Follow-Up', 'Issue', 'Other'],
    )


# ---------------------------------------------------------------------------
# 8. Product Pricing Quick Reference
# ---------------------------------------------------------------------------
@sales.route('/products')
def products():
    """Search product/item catalog for pricing and descriptions."""
    q = request.args.get('q', '').strip()
    items = []
    if q:
        items = ERPMirrorPick.query.filter(
            ERPMirrorPick.item_number.ilike(f'%{q}%')
            | ERPMirrorPick.description.ilike(f'%{q}%')
        ).with_entities(
            ERPMirrorPick.item_number,
            ERPMirrorPick.description,
        ).distinct(ERPMirrorPick.item_number).limit(100).all()

    return render_template(
        'sales/products.html',
        q=q,
        items=items,
    )


# ---------------------------------------------------------------------------
# 9. Sales Analytics & Reports
# ---------------------------------------------------------------------------
@sales.route('/reports')
def reports():
    """YOY trends, top customers, branch comparisons, product category trends."""
    period_days = request.args.get('period', 30, type=int)
    since = datetime.utcnow() - timedelta(days=period_days)

    # Orders per day over the period
    daily_orders = db.session.query(
        ERPMirrorPick.expect_date,
        func.count(distinct(ERPMirrorPick.so_number)).label('count'),
    ).filter(
        ERPMirrorPick.synced_at >= since,
        ERPMirrorPick.expect_date.isnot(None),
    ).group_by(ERPMirrorPick.expect_date).order_by(asc(ERPMirrorPick.expect_date)).all()

    # Top 15 customers
    top_customers = db.session.query(
        ERPMirrorPick.customer_name,
        func.count(distinct(ERPMirrorPick.so_number)).label('order_count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.customer_name).order_by(desc('order_count')).limit(15).all()

    # Orders by handling code / sale type
    by_sale_type = db.session.query(
        ERPMirrorPick.sale_type,
        func.count(distinct(ERPMirrorPick.so_number)).label('count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.sale_type).all()

    # Status breakdown
    status_breakdown = db.session.query(
        ERPMirrorPick.so_status,
        func.count(distinct(ERPMirrorPick.so_number)).label('count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.so_status).all()

    daily_labels = [r.expect_date or '' for r in daily_orders]
    daily_values = [r.count for r in daily_orders]

    return render_template(
        'sales/reports.html',
        period_days=period_days,
        daily_orders=daily_orders,
        top_customers=top_customers,
        by_sale_type=by_sale_type,
        status_breakdown=status_breakdown,
        daily_labels=daily_labels,
        daily_values=daily_values,
    )


# ---------------------------------------------------------------------------
# 10. Customer Statement / AR Snapshot
# ---------------------------------------------------------------------------
@sales.route('/customers/<customer_number>/statement')
def customer_statement(customer_number):
    """Open AR, recent invoices, balance, and credit limit usage."""
    customer_rows = ERPMirrorPick.query.filter(
        ERPMirrorPick.customer_name.ilike(f'%{customer_number}%')
        | ERPMirrorPick.so_number.ilike(f'%{customer_number}%')
    ).order_by(desc(ERPMirrorPick.expect_date)).all()

    customer_name = customer_rows[0].customer_name if customer_rows else customer_number

    open_orders = [r for r in customer_rows if r.so_status == 'O']
    invoiced_orders = [r for r in customer_rows if r.so_status in ('I', 'C')]

    return render_template(
        'sales/customer_statement.html',
        customer_number=customer_number,
        customer_name=customer_name,
        open_orders=open_orders,
        invoiced_orders=invoiced_orders,
    )

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from ..Models.models import CustomerNote
from sqlalchemy import desc
from datetime import datetime
from ..Services.erp_service import ERPService
from ..extensions import db
from ..branch_utils import normalize_branch
from ..auth import get_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_branch():
    """Read branch from URL param > session > empty (all branches)."""
    raw = request.args.get('branch', '').strip()
    if raw:
        return normalize_branch(raw) or ''
    return normalize_branch(session.get('selected_branch', '')) or ''


def _get_rep_id():
    """Return the logged-in user's ERP rep ID for filtering, or empty string.

    Sales-role users see their own orders by default.  Admin/ops users see all
    unless they explicitly opt in via ?my_orders=1.
    """
    user = get_current_user()
    if not user:
        return ''
    roles = set(user.get('roles') or [])
    # Admin/ops see everything unless they ask for "my orders"
    if roles & {'admin', 'ops'}:
        if request.args.get('my_orders', ''):
            return user.get('user_id', '') or ''
        return ''
    return user.get('user_id', '') or ''


sales = Blueprint('sales', __name__, url_prefix='/sales')
erp = ERPService()


def _value(row, key, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _format_timestamp(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%d %H:%M')
    return value or 'n/a'


def _format_date(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%d/%Y')
    return value or ''


def _normalize_order_row(row):
    return {
        'so_number': _value(row, 'so_number', ''),
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'address': _value(row, 'address', ''),
        'expect_date': _value(row, 'expect_date', ''),
        'expect_date_display': _format_date(_value(row, 'expect_date')),
        'reference': _value(row, 'reference', ''),
        'so_status': _value(row, 'so_status', ''),
        'handling_code': _value(row, 'handling_code', ''),
        'sale_type': _value(row, 'sale_type', ''),
        'ship_via': _value(row, 'ship_via', ''),
        'line_count': _value(row, 'line_count', 0),
        'salesperson': _value(row, 'salesperson', ''),
        'order_writer': _value(row, 'order_writer', ''),
        'po_number': _value(row, 'po_number', ''),
        'synced_at': _value(row, 'synced_at'),
        'synced_at_display': _format_timestamp(_value(row, 'synced_at')),
    }


def _normalize_product_row(row):
    return {
        'item_number': _value(row, 'item_number', ''),
        'description': _value(row, 'description', ''),
        'quantity_on_hand': _value(row, 'quantity_on_hand', 0) or 0,
    }


def _normalize_top_customer(row):
    return {
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'order_count': _value(row, 'order_count', 0) or 0,
    }


def _normalize_status_breakdown(row):
    return {
        'so_status': _value(row, 'so_status', ''),
        'count': _value(row, 'count', 0) or 0,
    }


def _normalize_daily_order(row):
    expect_date = _value(row, 'expect_date', '')
    if hasattr(expect_date, 'strftime'):
        expect_date = expect_date.strftime('%Y-%m-%d')
    return {
        'expect_date': expect_date or '',
        'count': _value(row, 'count', 0) or 0,
    }


# ---------------------------------------------------------------------------
# Hub — personalized sales dashboard
# ---------------------------------------------------------------------------

@sales.route('/')
@sales.route('/hub')
def hub():
    """Personalized sales dashboard — orientation page and workspace launcher."""
    user = get_current_user()
    rep_id = _get_rep_id()
    branch = _get_branch()

    metrics = erp.get_sales_hub_metrics(rep_id=rep_id)
    recent_orders = [
        _normalize_order_row(r) for r in erp.get_sales_order_status(
            rep_id=rep_id, limit=15, branch=branch,
        )
    ]
    recent_notes = CustomerNote.query.order_by(desc(CustomerNote.created_at)).limit(5).all()

    # Period-based report data (absorbed from rep_dashboard)
    period_days = request.args.get('period', 30, type=int)
    if period_days not in (7, 30, 90):
        period_days = 30
    reports = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    top_customers = [_normalize_top_customer(r) for r in reports.get('top_customers', [])]
    status_breakdown = [_normalize_status_breakdown(r) for r in reports.get('status_breakdown', [])]

    return render_template(
        'sales/hub.html',
        open_orders_count=metrics['open_orders_count'],
        total_orders_today=metrics['total_orders_today'],
        recent_orders=recent_orders,
        recent_notes=recent_notes,
        period_days=period_days,
        top_customers=top_customers,
        status_breakdown=status_breakdown,
        rep_id=rep_id,
        user=user,
    )


@sales.route('/rep-dashboard')
def rep_dashboard():
    """Redirect legacy rep-dashboard URL to the hub."""
    return redirect(url_for('sales.hub', **request.args))


# ---------------------------------------------------------------------------
# Customer Workspace
# ---------------------------------------------------------------------------

@sales.route('/customer-profile/<customer_number>')
def customer_profile(customer_number):
    """Customer workspace — account overview with quick actions and cross-navigation."""
    customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=50)]
    order_numbers = list({r['so_number'] for r in customer_rows if r.get('so_number')})
    first_row = customer_rows[0] if customer_rows else {}
    customer_name = first_row.get('customer_name') or customer_number

    # Customer master details and ship-to addresses
    customer_details = erp.get_customer_details(customer_number)
    ship_to_addresses = erp.get_customer_ship_to_addresses(customer_number)

    notes = CustomerNote.query.filter_by(
        customer_number=customer_number
    ).order_by(desc(CustomerNote.created_at)).limit(10).all()

    open_orders = [r for r in customer_rows if r.get('so_status') == 'O']

    return render_template(
        'sales/customer_profile.html',
        customer_number=customer_number,
        customer_name=customer_name,
        customer_details=customer_details,
        customer_rows=customer_rows,
        order_numbers=order_numbers,
        notes=notes,
        recent_orders=customer_rows[:10],
        open_orders=open_orders,
        ship_to_addresses=ship_to_addresses,
    )


@sales.route('/customer-notes/<customer_number>', methods=['GET', 'POST'])
def customer_notes(customer_number):
    """View and add internal notes about a customer."""
    if request.method == 'POST':
        note_type = request.form.get('note_type', 'Call')
        body = request.form.get('body', '').strip()
        rep_name = request.form.get('rep_name', '').strip()
        if not rep_name:
            user = get_current_user()
            rep_name = (user.get('display_name') or user.get('user_id', '')) if user else ''
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

    customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=1)]
    customer_row = customer_rows[0] if customer_rows else {}
    customer_name = customer_row.get('customer_name') or customer_number

    return render_template(
        'sales/customer_notes.html',
        customer_number=customer_number,
        customer_name=customer_name,
        notes=notes,
        note_types=['Call', 'Visit', 'Email', 'Quote Follow-Up', 'Issue', 'Other'],
    )


@sales.route('/customer-statement/<customer_number>')
def customer_statement(customer_number):
    """Account statement — open orders and invoiced orders for a customer."""
    customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=100)]
    customer_row = customer_rows[0] if customer_rows else {}
    customer_name = customer_row.get('customer_name') or customer_number
    customer_details = erp.get_customer_details(customer_number)

    open_orders = [r for r in customer_rows if r.get('so_status') == 'O']
    invoiced_orders = [r for r in customer_rows if r.get('so_status') in ('I', 'C')]

    return render_template(
        'sales/customer_statement.html',
        customer_number=customer_number,
        customer_name=customer_name,
        customer_details=customer_details,
        open_orders=open_orders,
        invoiced_orders=invoiced_orders,
        now=datetime.now(),
    )


@sales.route('/customer/<customer_number>')
def customer_shortcut(customer_number):
    """Short URL alias for customer profile."""
    return redirect(url_for('sales.customer_profile', customer_number=customer_number))


# ---------------------------------------------------------------------------
# Sales Transaction Workspace  (replaces order_status + invoice_lookup)
# ---------------------------------------------------------------------------

PAGE_SIZE = 50


@sales.route('/transactions')
def transactions():
    """Unified sales transaction workspace — search and act on all orders."""
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    page = request.args.get('page', 1, type=int)
    page = max(1, page)
    my_orders = request.args.get('my_orders', '')

    # Determine if we should filter to open only or show all statuses
    open_only = not status and not date_from and not date_to and not q

    orders = [
        _normalize_order_row(r) for r in erp.get_sales_order_status(
            q=q, limit=PAGE_SIZE, branch=branch, open_only=open_only,
            rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
            page=page,
        )
    ]

    # Status counts for the summary bar
    status_counts = {}
    for o in orders:
        s = o.get('so_status', '')
        status_counts[s] = status_counts.get(s, 0) + 1

    return render_template(
        'sales/transactions.html',
        orders=orders,
        q=q,
        status=status,
        date_from=date_from,
        date_to=date_to,
        branch=branch,
        rep_id=rep_id,
        my_orders=my_orders,
        page=page,
        page_size=PAGE_SIZE,
        has_next=len(orders) == PAGE_SIZE,
        status_counts=status_counts,
    )


# Legacy URL redirects — old routes now served by /transactions
@sales.route('/order-status')
def order_status():
    return redirect(url_for('sales.transactions', status='O', **{
        k: v for k, v in request.args.items() if k != 'status'
    }))


@sales.route('/invoice-lookup')
def invoice_lookup():
    return redirect(url_for('sales.transactions', status='I,C', **{
        k: v for k, v in request.args.items() if k != 'status'
    }))


# ---------------------------------------------------------------------------
# Purchase History Workspace  (evolved from order_history)
# ---------------------------------------------------------------------------

@sales.route('/history', defaults={'customer_number': ''})
@sales.route('/history/<customer_number>')
def history(customer_number):
    """Historical purchase and pricing research workspace."""
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    page = request.args.get('page', 1, type=int)
    page = max(1, page)
    # Accept customer_number from URL path OR query param
    if not customer_number:
        customer_number = request.args.get('customer_number', '').strip()
    searched = bool(customer_number or q or date_from or date_to or status or branch)

    history_rows = []
    if searched:
        history_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(
            customer_number, q=q, date_from=date_from, date_to=date_to, status=status,
            branch=branch, limit=PAGE_SIZE, page=page, rep_id=rep_id,
        )]
    return render_template(
        'sales/history.html',
        history=history_rows,
        customer_number=customer_number,
        q=q, date_from=date_from, date_to=date_to, status=status, branch=branch,
        searched=searched,
        page=page,
        page_size=PAGE_SIZE,
        has_next=len(history_rows) == PAGE_SIZE,
        rep_id=rep_id,
    )


# Legacy URL redirect
@sales.route('/order-history', defaults={'customer_number': ''})
@sales.route('/order-history/<customer_number>')
def order_history(customer_number):
    args = dict(request.args)
    if customer_number:
        args['customer_number'] = customer_number
    return redirect(url_for('sales.history', **args))


# ---------------------------------------------------------------------------
# Supporting pages
# ---------------------------------------------------------------------------

@sales.route('/products')
def products():
    """Product catalog with stock levels."""
    q = request.args.get('q', '').strip()
    products_list = []
    if q:
        products_list = [_normalize_product_row(r) for r in erp.get_sales_products(q=q, limit=50)]
    return render_template('sales/products.html', products=products_list, q=q)


@sales.route('/reports')
def reports():
    """Sales analytics and territory reports."""
    period_days = request.args.get('period', 30, type=int)
    branch = _get_branch()
    rep_id = _get_rep_id()
    report_data = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    daily_orders = [_normalize_daily_order(r) for r in report_data['daily_orders']]
    top_customers = [_normalize_top_customer(r) for r in report_data['top_customers']]
    status_breakdown = [_normalize_status_breakdown(r) for r in report_data['status_breakdown']]
    daily_labels = [r['expect_date'] for r in daily_orders]
    daily_values = [r['count'] for r in daily_orders]

    return render_template(
        'sales/reports.html',
        period_days=period_days,
        branch=branch,
        daily_orders=daily_orders,
        top_customers=top_customers,
        status_breakdown=status_breakdown,
        daily_labels=daily_labels,
        daily_values=daily_values,
        rep_id=rep_id,
    )


# ---------------------------------------------------------------------------
# JSON API endpoints
# ---------------------------------------------------------------------------

@sales.route('/api/transactions')
def api_transactions():
    """JSON endpoint for transaction workspace — supports AJAX filtering."""
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    limit = min(int(request.args.get('limit', 100)), 500)
    page = request.args.get('page', 1, type=int)
    open_only = not status and not date_from and not date_to and not q
    orders = [
        _normalize_order_row(r) for r in erp.get_sales_order_status(
            q=q, limit=limit, branch=branch, open_only=open_only,
            rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
            page=page,
        )
    ]
    return jsonify(orders)


# Keep old API endpoint working
@sales.route('/api/orders')
def api_orders():
    """Legacy JSON endpoint — redirects to api_transactions."""
    return api_transactions()


@sales.route('/api/customers/search')
def api_customer_search():
    """JSON endpoint for customer type-ahead."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    rows = erp.get_sales_customers_search(q=q, limit=10)
    results = []
    seen = set()
    for r in rows:
        key = _value(r, 'cust_code') or ''
        name = _value(r, 'cust_name') or key
        if key and key not in seen:
            seen.add(key)
            results.append({
                'title': name,
                'subtitle': f"Customer # {key}",
                'url': url_for('sales.customer_profile', customer_number=key),
            })
    return jsonify(results)

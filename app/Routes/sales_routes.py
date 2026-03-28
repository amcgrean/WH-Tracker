import logging
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from ..Models.models import CustomerNote
from sqlalchemy import desc
from datetime import datetime, date, timedelta
from ..Services.erp_service import ERPService
from ..extensions import db
from ..branch_utils import normalize_branch
from ..auth import get_current_user

logger = logging.getLogger(__name__)


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


def _normalize_order_row(row, rep_id=''):
    salesperson = _value(row, 'salesperson', '')
    order_writer = _value(row, 'order_writer', '')
    # Determine agent role relative to the logged-in user
    agent_role = ''
    if rep_id:
        is_agent1 = salesperson and salesperson == rep_id
        is_agent3 = order_writer and order_writer == rep_id
        if is_agent1 and is_agent3:
            agent_role = 'both'
        elif is_agent1:
            agent_role = 'acct_rep'
        elif is_agent3:
            agent_role = 'writer'
    return {
        'so_number': _value(row, 'so_number', ''),
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'address': _value(row, 'address', ''),
        'expect_date': _value(row, 'expect_date', ''),
        'expect_date_display': _format_date(_value(row, 'expect_date')),
        'ship_date': _value(row, 'ship_date', ''),
        'ship_date_display': _format_date(_value(row, 'ship_date')),
        'invoice_date': _value(row, 'invoice_date', ''),
        'invoice_date_display': _format_date(_value(row, 'invoice_date')),
        'reference': _value(row, 'reference', ''),
        'so_status': _value(row, 'so_status', ''),
        'handling_code': _value(row, 'handling_code', ''),
        'sale_type': _value(row, 'sale_type', ''),
        'ship_via': _value(row, 'ship_via', ''),
        'line_count': _value(row, 'line_count', 0),
        'salesperson': salesperson,
        'order_writer': order_writer,
        'agent_role': agent_role,
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

    try:
        metrics = erp.get_sales_hub_metrics(rep_id=rep_id)
    except Exception as e:
        logger.error("Sales hub metrics failed: %s", e)
        metrics = {"open_orders_count": 0, "total_orders_today": 0}

    try:
        recent_orders = [
            _normalize_order_row(r) for r in erp.get_sales_order_status(
                rep_id=rep_id, limit=15, branch=branch,
            )
        ]
    except Exception as e:
        logger.error("Sales hub recent orders failed: %s", e)
        recent_orders = []

    try:
        recent_notes = CustomerNote.query.order_by(desc(CustomerNote.created_at)).limit(5).all()
    except Exception as e:
        logger.error("Sales hub recent notes failed: %s", e)
        recent_notes = []

    # Period-based report data (absorbed from rep_dashboard)
    period_days = request.args.get('period', 30, type=int)
    if period_days not in (7, 30, 90):
        period_days = 30

    try:
        reports = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    except Exception as e:
        logger.error("Sales hub reports failed: %s", e)
        reports = {"top_customers": [], "status_breakdown": []}

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
    try:
        customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=50)]
    except Exception as e:
        logger.error("Customer profile orders failed for %s: %s", customer_number, e)
        customer_rows = []

    order_numbers = list({r['so_number'] for r in customer_rows if r.get('so_number')})
    first_row = customer_rows[0] if customer_rows else {}
    customer_name = first_row.get('customer_name') or customer_number

    try:
        customer_details = erp.get_customer_details(customer_number)
    except Exception as e:
        logger.error("Customer details failed for %s: %s", customer_number, e)
        customer_details = {}

    try:
        ship_to_addresses = erp.get_customer_ship_to_addresses(customer_number)
    except Exception as e:
        logger.error("Customer ship-to addresses failed for %s: %s", customer_number, e)
        ship_to_addresses = []

    try:
        notes = CustomerNote.query.filter_by(
            customer_number=customer_number
        ).order_by(desc(CustomerNote.created_at)).limit(10).all()
    except Exception as e:
        logger.error("Customer notes query failed for %s: %s", customer_number, e)
        notes = []

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

    try:
        notes = CustomerNote.query.filter_by(
            customer_number=customer_number
        ).order_by(desc(CustomerNote.created_at)).all()
    except Exception as e:
        logger.error("Customer notes query failed for %s: %s", customer_number, e)
        notes = []

    try:
        customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=1)]
    except Exception as e:
        logger.error("Customer notes order lookup failed for %s: %s", customer_number, e)
        customer_rows = []
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
    try:
        customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=100)]
    except Exception as e:
        logger.error("Customer statement orders failed for %s: %s", customer_number, e)
        customer_rows = []
    customer_row = customer_rows[0] if customer_rows else {}
    customer_name = customer_row.get('customer_name') or customer_number
    try:
        customer_details = erp.get_customer_details(customer_number)
    except Exception as e:
        logger.error("Customer statement details failed for %s: %s", customer_number, e)
        customer_details = {}

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


CLOSED_CM_STATUSES = ('I', 'C', 'X', 'CAN', 'CANCEL', 'CANCELED', 'CN', 'VOID')
# Sale types excluded from "delivery / add-on" view (leaves only delivery-style orders)
NON_DELIVERY_TYPES = ('Direct', 'WillCall', 'XInstall', 'Hold', 'CM')

VIEW_PRESETS = {
    'my_open_3d': {
        'label': 'My Open Orders', 'sublabel': 'Next 3 Days',
        'icon': 'fa-clock', 'color': 'success', 'section': 'my',
    },
    'my_open_7d': {
        'label': 'My Open Orders', 'sublabel': 'Next 7 Days',
        'icon': 'fa-calendar-week', 'color': 'primary', 'section': 'my',
    },
    'branch_delivery': {
        'label': 'Branch Orders', 'sublabel': 'Delivery / Add On',
        'icon': 'fa-truck', 'color': 'info', 'section': 'branch',
    },
    'branch_willcall': {
        'label': 'Branch Orders', 'sublabel': 'Will Call',
        'icon': 'fa-store', 'color': 'warning', 'section': 'branch',
    },
    'my_rma': {
        'label': 'My Open RMAs', 'sublabel': 'Credit Memos',
        'icon': 'fa-undo-alt', 'color': 'danger', 'section': 'my',
    },
    'my_shipped_2d': {
        'label': 'My Shipped', 'sublabel': 'Last 2 Days',
        'icon': 'fa-shipping-fast', 'color': 'teal', 'section': 'my',
    },
    'my_invoiced_5d': {
        'label': 'My Invoiced', 'sublabel': 'Last 5 Days',
        'icon': 'fa-file-invoice-dollar', 'color': 'secondary', 'section': 'my',
    },
}


def _get_user_rep_id():
    """Return the logged-in user's raw ERP rep ID (regardless of role)."""
    user = get_current_user()
    if not user:
        return ''
    return user.get('user_id', '') or ''


@sales.route('/transactions')
def transactions():
    """Unified sales transaction workspace — search and act on all orders."""
    view = request.args.get('view', '').strip()
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    user_rep_id = _get_user_rep_id()
    page = request.args.get('page', 1, type=int)
    page = max(1, page)
    my_orders = request.args.get('my_orders', '')
    today = date.today()

    # --- View presets override manual filters ---
    active_view = view if view in VIEW_PRESETS else ''
    sale_type = ''
    exclude_sale_types = ''
    use_shipment_query = False
    shipment_date_field = ''

    if active_view == 'my_open_3d':
        status = 'O'
        date_from = today.isoformat()
        date_to = (today + timedelta(days=3)).isoformat()
        rep_id = user_rep_id
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
    elif active_view == 'my_open_7d':
        status = 'O'
        date_from = today.isoformat()
        date_to = (today + timedelta(days=7)).isoformat()
        rep_id = user_rep_id
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
    elif active_view == 'branch_delivery':
        status = 'O'
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
        rep_id = ''  # branch-wide, not filtered to user
    elif active_view == 'branch_willcall':
        status = 'O'
        sale_type = 'WillCall'
        rep_id = ''  # branch-wide
    elif active_view == 'my_rma':
        sale_type = 'CM'
        # Open CMs: exclude closed/cancelled statuses
        open_cm_statuses = [s for s in ('O', 'H') if len(s) == 1]
        status = ','.join(open_cm_statuses)
        date_from = ''
        date_to = ''
        rep_id = user_rep_id
    elif active_view == 'my_shipped_2d':
        use_shipment_query = True
        shipment_date_field = 'ship_date'
        date_from = (today - timedelta(days=2)).isoformat()
        date_to = today.isoformat()
        rep_id = user_rep_id
    elif active_view == 'my_invoiced_5d':
        use_shipment_query = True
        shipment_date_field = 'invoice_date'
        date_from = (today - timedelta(days=5)).isoformat()
        date_to = today.isoformat()
        rep_id = user_rep_id

    # Determine if we should filter to open only or show all statuses
    open_only = not active_view and not status and not date_from and not date_to and not q

    try:
        if use_shipment_query:
            orders = [
                _normalize_order_row(r, rep_id=user_rep_id) for r in erp.get_orders_by_shipment_date(
                    date_field=shipment_date_field,
                    date_from=date_from, date_to=date_to,
                    rep_id=rep_id, branch=branch, limit=PAGE_SIZE, page=page,
                )
            ]
        else:
            orders = [
                _normalize_order_row(r, rep_id=user_rep_id) for r in erp.get_sales_order_status(
                    q=q, limit=PAGE_SIZE, branch=branch, open_only=open_only,
                    rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
                    page=page, sale_type=sale_type, exclude_sale_types=exclude_sale_types,
                )
            ]
    except Exception as e:
        logger.error("Transactions query failed: %s", e)
        orders = []

    # Status counts for the summary bar
    status_counts = {}
    for o in orders:
        s = o.get('so_status', '')
        status_counts[s] = status_counts.get(s, 0) + 1

    return render_template(
        'sales/transactions.html',
        orders=orders,
        q=q,
        status=status if not active_view else '',
        date_from=date_from if not active_view else '',
        date_to=date_to if not active_view else '',
        branch=branch,
        rep_id=rep_id,
        user_rep_id=user_rep_id,
        my_orders=my_orders,
        page=page,
        page_size=PAGE_SIZE,
        has_next=len(orders) == PAGE_SIZE,
        status_counts=status_counts,
        active_view=active_view,
        view_presets=VIEW_PRESETS,
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
        try:
            history_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(
                customer_number, q=q, date_from=date_from, date_to=date_to, status=status,
                branch=branch, limit=PAGE_SIZE, page=page, rep_id=rep_id,
            )]
        except Exception as e:
            logger.error("Purchase history query failed: %s", e)
            history_rows = []
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
        try:
            products_list = [_normalize_product_row(r) for r in erp.get_sales_products(q=q, limit=50)]
        except Exception as e:
            logger.error("Products query failed: %s", e)
    return render_template('sales/products.html', products=products_list, q=q)


@sales.route('/reports')
def reports():
    """Sales analytics and territory reports."""
    period_days = request.args.get('period', 30, type=int)
    branch = _get_branch()
    rep_id = _get_rep_id()
    try:
        report_data = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    except Exception as e:
        logger.error("Sales reports query failed: %s", e)
        report_data = {"daily_orders": [], "top_customers": [], "status_breakdown": []}
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
    try:
        orders = [
            _normalize_order_row(r) for r in erp.get_sales_order_status(
                q=q, limit=limit, branch=branch, open_only=open_only,
                rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
                page=page,
            )
        ]
    except Exception as e:
        logger.error("API transactions query failed: %s", e)
        orders = []
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
    try:
        rows = erp.get_sales_customers_search(q=q, limit=10)
    except Exception as e:
        logger.error("Customer search failed: %s", e)
        return jsonify([])
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

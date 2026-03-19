from flask import Blueprint, render_template, request, flash, redirect, url_for
from ..Models.models import CustomerNote
from sqlalchemy import desc
from datetime import datetime
from ..Services.erp_service import ERPService
from ..extensions import db

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


def _normalize_order_row(row):
    return {
        'so_number': _value(row, 'so_number', ''),
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'expect_date': _value(row, 'expect_date', ''),
        'reference': _value(row, 'reference', ''),
        'so_status': _value(row, 'so_status', ''),
        'handling_code': _value(row, 'handling_code', ''),
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


@sales.route('/')
@sales.route('/hub')
def hub():
    """Main sales team landing page/dashboard."""
    metrics = erp.get_sales_hub_metrics()
    recent_notes = CustomerNote.query.order_by(desc(CustomerNote.created_at)).limit(5).all()

    return render_template(
        'sales/hub.html',
        open_orders_count=metrics['open_orders_count'],
        total_orders_today=metrics['total_orders_today'],
        recent_notes=recent_notes,
    )


@sales.route('/rep-dashboard')
def rep_dashboard():
    """Specific personalized dashboard for a sales rep."""
    stats = erp.get_sales_rep_metrics(period_days=30)
    return render_template('sales/rep_dashboard.html', stats=stats)


@sales.route('/customer-profile/<customer_number>')
def customer_profile(customer_number):
    """Detailed profile for a specific customer."""
    customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=200)]
    order_numbers = list({r['so_number'] for r in customer_rows if r.get('so_number')})
    first_row = customer_rows[0] if customer_rows else {}
    customer_name = first_row.get('customer_name') or customer_number

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
        recent_orders=customer_rows[:10],
    )


@sales.route('/order-status')
def order_status():
    """Searchable/filterable view of all open orders."""
    q = request.args.get('q', '').strip()
    orders = [_normalize_order_row(r) for r in erp.get_sales_order_status(q=q, limit=100)]
    return render_template('sales/order_status.html', orders=orders, q=q)


@sales.route('/customer-notes/<customer_number>', methods=['GET', 'POST'])
def customer_notes(customer_number):
    """View and add internal notes about a customer."""
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


@sales.route('/invoice-lookup')
def invoice_lookup():
    """Simple tool to find invoices by number or date."""
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    invoices = [_normalize_order_row(r) for r in erp.get_sales_invoice_lookup(q=q, date_from=date_from, date_to=date_to, limit=50)]
    return render_template('sales/invoice_lookup.html', invoices=invoices, q=q, date_from=date_from, date_to=date_to)


@sales.route('/products')
def products():
    """Product catalog with stock levels and pricing."""
    q = request.args.get('q', '').strip()
    products_list = [_normalize_product_row(r) for r in erp.get_sales_products(q=q, limit=50)]
    return render_template('sales/products.html', products=products_list, q=q)


@sales.route('/reports')
def reports():
    """Sales analytics and territory reports."""
    period_days = request.args.get('period', 30, type=int)
    report_data = erp.get_sales_reports(period_days=period_days)
    daily_orders = [_normalize_daily_order(r) for r in report_data['daily_orders']]
    top_customers = [_normalize_top_customer(r) for r in report_data['top_customers']]
    status_breakdown = [_normalize_status_breakdown(r) for r in report_data['status_breakdown']]
    daily_labels = [r['expect_date'] for r in daily_orders]
    daily_values = [r['count'] for r in daily_orders]

    return render_template(
        'sales/reports.html',
        period_days=period_days,
        daily_orders=daily_orders,
        top_customers=top_customers,
        status_breakdown=status_breakdown,
        daily_labels=daily_labels,
        daily_values=daily_values,
    )


@sales.route('/customer-statement/<customer_number>')
def customer_statement(customer_number):
    """Generate a simple summary statement for a customer."""
    customer_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, limit=1)]
    customer_row = customer_rows[0] if customer_rows else {}
    customer_name = customer_row.get('customer_name') or customer_number
    now = datetime.now()

    return render_template(
        'sales/customer_statement.html',
        customer_number=customer_number,
        customer_name=customer_name,
        now=now,
    )


@sales.route('/awards')
def awards():
    """Sales gamification / awards page."""
    return render_template('sales/awards.html')


@sales.route('/order-history', defaults={'customer_number': ''})
@sales.route('/order-history/<customer_number>')
def order_history(customer_number):
    """Full order history for a customer."""
    q = request.args.get('q', '').strip()
    history = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(customer_number, q=q, limit=None if customer_number else 200)]
    return render_template('sales/order_history.html', history=history, customer_number=customer_number, q=q)

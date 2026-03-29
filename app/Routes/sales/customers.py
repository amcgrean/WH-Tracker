import logging
from datetime import datetime
from flask import render_template, request, flash, redirect, url_for
from sqlalchemy import desc
from app.Models.models import CustomerNote
from app.extensions import db
from app.auth import get_current_user
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _normalize_order_row, _normalize_product_row, erp,
)

logger = logging.getLogger(__name__)


@sales_bp.route('/customer-profile/<customer_number>')
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

    open_orders = [r for r in customer_rows if str(r.get('so_status', '')).upper() == 'O']

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


@sales_bp.route('/customer-notes/<customer_number>', methods=['GET', 'POST'])
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


@sales_bp.route('/customer-statement/<customer_number>')
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

    open_orders = [r for r in customer_rows if str(r.get('so_status', '')).upper() == 'O']
    invoiced_orders = [r for r in customer_rows if str(r.get('so_status', '')).upper() in ('I', 'C')]

    return render_template(
        'sales/customer_statement.html',
        customer_number=customer_number,
        customer_name=customer_name,
        customer_details=customer_details,
        open_orders=open_orders,
        invoiced_orders=invoiced_orders,
        now=datetime.now(),
    )


@sales_bp.route('/customer/<customer_number>')
def customer_shortcut(customer_number):
    """Short URL alias for customer profile."""
    return redirect(url_for('sales.customer_profile', customer_number=customer_number))


@sales_bp.route('/products')
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

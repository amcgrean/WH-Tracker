from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from ..Models.models import ERPMirrorPick, CustomerNote, db
from sqlalchemy import func, desc, distinct
from datetime import datetime, timedelta

sales = Blueprint('sales', __name__, url_prefix='/sales')

@sales.route('/')
@sales.route('/hub')
def hub():
    """Main sales team landing page/dashboard."""
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

@sales.route('/rep-dashboard')
def rep_dashboard():
    """Specific personalized dashboard for a sales rep."""
    # Aggregating some metrics from mirror
    period_days = 30
    since = datetime.utcnow() - timedelta(days=period_days)
    
    active_customers = db.session.query(func.count(distinct(ERPMirrorPick.customer_name))).filter(
        ERPMirrorPick.synced_at >= since
    ).scalar() or 0
    
    # Mocking some metrics for now
    stats = {
        'active_customers': active_customers,
        'open_orders_value': 125400,
        'monthly_goal_progress': 75
    }
    return render_template('sales/rep_dashboard.html', stats=stats)

@sales.route('/customer-profile/<customer_number>')
def customer_profile(customer_number):
    """Detailed profile for a specific customer."""
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
        recent_orders=customer_rows[:10]
    )

@sales.route('/order-status')
def order_status():
    """Searchable/filterable view of all open orders."""
    q = request.args.get('q', '').strip()
    query = ERPMirrorPick.query.filter(ERPMirrorPick.so_status == 'O')
    
    if q:
        query = query.filter(
            ERPMirrorPick.so_number.ilike(f'%{q}%')
            | ERPMirrorPick.customer_name.ilike(f'%{q}%')
        )
        
    orders = query.order_by(desc(ERPMirrorPick.synced_at)).limit(100).all()
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

@sales.route('/invoice-lookup')
def invoice_lookup():
    """Simple tool to find invoices by number or date."""
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
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

    invoices = query.order_by(desc(ERPMirrorPick.synced_at)).limit(50).all()
    return render_template('sales/invoice_lookup.html', invoices=invoices, q=q, date_from=date_from, date_to=date_to)

@sales.route('/products')
def products():
    """Product catalog with stock levels and pricing."""
    q = request.args.get('q', '').strip()
    query = ERPMirrorPick.query
    
    if q:
        query = query.filter(
            ERPMirrorPick.item_number.ilike(f'%{q}%')
            | ERPMirrorPick.description.ilike(f'%{q}%')
        )
        
    products_list = query.with_entities(
        ERPMirrorPick.item_number,
        ERPMirrorPick.description,
        ERPMirrorPick.qty.label('quantity_on_hand') # Using qty as proxy for stock for now
    ).distinct(ERPMirrorPick.item_number).limit(50).all()
    
    return render_template('sales/products.html', products=products_list, q=q)

@sales.route('/reports')
def reports():
    """Sales analytics and territory reports."""
    period_days = request.args.get('period', 30, type=int)
    since = datetime.utcnow() - timedelta(days=period_days)
    
    # Orders per day over the period
    daily_orders = db.session.query(
        ERPMirrorPick.expect_date,
        func.count(distinct(ERPMirrorPick.so_number)).label('count'),
    ).filter(
        ERPMirrorPick.synced_at >= since,
        ERPMirrorPick.expect_date.isnot(None),
    ).group_by(ERPMirrorPick.expect_date).order_by(ERPMirrorPick.expect_date.asc()).all()

    # Top 15 customers
    top_customers = db.session.query(
        ERPMirrorPick.customer_name,
        func.count(distinct(ERPMirrorPick.so_number)).label('order_count'),
    ).filter(
        ERPMirrorPick.synced_at >= since
    ).group_by(ERPMirrorPick.customer_name).order_by(desc('order_count')).limit(15).all()

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
        status_breakdown=status_breakdown,
        daily_labels=daily_labels,
        daily_values=daily_values,
    )

@sales.route('/customer-statement/<customer_number>')
def customer_statement(customer_number):
    """Generate a simple summary statement for a customer."""
    customer_rows = ERPMirrorPick.query.filter(
        ERPMirrorPick.customer_name.ilike(f'%{customer_number}%')
        | (ERPMirrorPick.so_number.ilike(f'%{customer_number}%'))
    ).order_by(desc(ERPMirrorPick.expect_date)).all()

    customer_name = customer_rows[0].customer_name if customer_rows else customer_number
    now = datetime.now()

    return render_template(
        'sales/customer_statement.html',
        customer_number=customer_number,
        customer_name=customer_name,
        now=now
    )

@sales.route('/awards')
def awards():
    """Sales gamification / awards page."""
    return render_template('sales/awards.html')

@sales.route('/order-history/<customer_number>')
def order_history(customer_number):
    """Full order history for a customer."""
    history = ERPMirrorPick.query.filter(
        ERPMirrorPick.customer_name.ilike(f'%{customer_number}%')
        | (ERPMirrorPick.so_number.ilike(f'%{customer_number}%'))
    ).all()
    return render_template('sales/order_history.html', history=history, customer_number=customer_number)

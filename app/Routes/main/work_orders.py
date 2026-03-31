import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash

from app.extensions import db
from app.Models.models import Pickster, WorkOrderAssignment, AuditEvent
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import CHUNK_SIZE, parse_selected_work_order_payload, normalize_so_number


@main_bp.route('/work_orders')
def work_orders():
    # Page 1: Select User - Filter for Door Builders
    pickers = Pickster.query.filter_by(user_type='door_builder').order_by(Pickster.name).all()
    return render_template('work_order/user_selection.html', pickers=pickers)


@main_bp.route('/work_orders/open/<int:user_id>')
def work_orders_open(user_id):
    # Page 2: Open Work Orders
    user = Pickster.query.get_or_404(user_id)
    open_orders = WorkOrderAssignment.query.filter(
        WorkOrderAssignment.assigned_to_id == user.id,
        WorkOrderAssignment.status.in_(['Open', 'Assigned']),
    ).order_by(WorkOrderAssignment.created_at.desc()).all()
    return render_template('work_order/open_orders.html', user=user, open_orders=open_orders)


@main_bp.route('/work_orders/complete/<int:wo_id>', methods=['POST'])
def complete_work_order(wo_id):
    wo = WorkOrderAssignment.query.get_or_404(wo_id)
    now = datetime.utcnow()
    wo.status = 'Complete'
    wo.completed_at = now
    wo.completed_by_id = wo.assigned_to_id  # the assigned worker is completing it

    audit = AuditEvent(
        event_type='wo_completed',
        entity_type='work_order',
        entity_id=wo.id,
        so_number=wo.sales_order_number,
        actor_id=wo.assigned_to_id,
        occurred_at=now,
    )
    db.session.add(audit)
    db.session.commit()
    flash(f'Work Order {wo.work_order_number} completed!')
    return redirect(url_for('main.work_orders_open', user_id=wo.assigned_to_id))


@main_bp.route('/work_orders/scan/<int:user_id>')
def work_order_scan(user_id):
    # Page 3: Scan Barcode
    user = Pickster.query.get_or_404(user_id)
    return render_template('work_order/scan_barcode.html', user=user)


@main_bp.route('/work_orders/select')
def work_order_select():
    # Page 4: Select Work Orders (Live Lookup)
    user_id = request.args.get('user_id')
    barcode = normalize_so_number((request.args.get('barcode') or '').strip())
    if not user_id or not barcode:
        flash('A user and sales order barcode are required.', 'warning')
        return redirect(url_for('main.work_orders'))

    user = Pickster.query.get_or_404(user_id)

    erp = ERPService()
    items = erp.get_work_orders_by_barcode(barcode)

    return render_template('work_order/select_orders.html', user=user, barcode=barcode, items=items)


@main_bp.route('/work_orders/start', methods=['POST'])
def start_work_orders():
    user_id = request.form.get('user_id', type=int)
    selected_items = request.form.getlist('selected_items')

    if not user_id:
        flash('A builder selection is required before starting work orders.', 'danger')
        return redirect(url_for('main.work_orders'))
    if not selected_items:
        flash('Select at least one work order to start.', 'warning')
        return redirect(url_for('main.work_order_scan', user_id=user_id))

    created = 0
    skipped = 0
    for item_str in selected_items:
        payload = parse_selected_work_order_payload(item_str)
        if not payload or not payload['wo_id']:
            skipped += 1
            continue

        existing = WorkOrderAssignment.query.filter_by(wo_id=payload['wo_id']).first()
        if existing:
            existing.sales_order_number = payload['so_number'] or existing.sales_order_number
            existing.item_number = payload['item_number'] or existing.item_number
            existing.description = payload['description'] or existing.description
            existing.assigned_to_id = user_id
            if existing.status != 'Complete':
                existing.status = 'Assigned'
            created += 1
            continue

        new_wo = WorkOrderAssignment(
            sales_order_number=payload['so_number'] or 'UNKNOWN',
            wo_id=payload['wo_id'],
            item_number=payload['item_number'],
            description=payload['description'],
            status='Assigned',
            assigned_to_id=user_id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_wo)
        created += 1

    db.session.commit()
    message = f'{created} work order(s) queued for the builder.'
    if skipped:
        message += f' Skipped {skipped} invalid selection(s).'
    flash(message, 'success' if created else 'warning')
    return redirect(url_for('main.work_orders_open', user_id=user_id))

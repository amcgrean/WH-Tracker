from datetime import datetime
from flask import render_template, request, redirect, url_for, flash

from app.extensions import db
from app.Models.models import Pickster, Pick, WorkOrderAssignment, AuditEvent
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import (
    WILL_CALL_TYPE_ID, ensure_pick_type_exists,
    parse_selected_work_order_payload, _kiosk_context,
)


@main_bp.route('/kiosk/<branch>/pickers')
def kiosk_pickers(branch):
    ctx = _kiosk_context(branch)
    normalized = ctx['kiosk_branch']
    pickers = Pickster.query.filter(
        (Pickster.user_type == 'picker') | (Pickster.user_type == None),
        (Pickster.branch_code == normalized) | (Pickster.branch_code == None),
    ).order_by(Pickster.name).all()
    return render_template('kiosk/pickers.html', pickers=pickers, **ctx)


@main_bp.route('/kiosk/<branch>/confirm/<int:picker_id>', methods=['GET', 'POST'])
def kiosk_confirm_picker(branch, picker_id):
    ctx = _kiosk_context(branch)
    picker = Pickster.query.get_or_404(picker_id)
    incomplete_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None).all()
    return render_template('kiosk/confirm_picker.html', picker=picker,
                           incomplete_picks=incomplete_picks, **ctx)


@main_bp.route('/kiosk/<branch>/pick/<int:picker_id>/<int:pick_type_id>', methods=['GET', 'POST'])
def kiosk_input_pick(branch, picker_id, pick_type_id):
    ctx = _kiosk_context(branch)
    picker = Pickster.query.get_or_404(picker_id)

    if not ensure_pick_type_exists(pick_type_id):
        flash('Invalid pick type selected.', 'error')
        return redirect(url_for('main.kiosk_pickers', branch=branch))

    if request.method == 'POST':
        barcode = request.form.get('barcode', '').strip()
        if barcode:
            start_time = datetime.utcnow()
            completed_time = start_time if pick_type_id == WILL_CALL_TYPE_ID else None
            new_pick = Pick(
                barcode_number=barcode,
                start_time=start_time,
                completed_time=completed_time,
                picker_id=picker.id,
                pick_type_id=pick_type_id,
                branch_code=ctx['kiosk_branch'],
            )
            db.session.add(new_pick)
            db.session.flush()
            audit = AuditEvent(
                event_type='pick_completed' if completed_time else 'pick_started',
                entity_type='pick',
                entity_id=new_pick.id,
                so_number=barcode,
                actor_id=picker.id,
                occurred_at=start_time,
            )
            db.session.add(audit)
            db.session.commit()
            flash('Pick recorded.' if completed_time else 'Pick started.')
            return redirect(url_for('main.kiosk_pickers', branch=branch))
        else:
            flash('Barcode is required.', 'error')

    return render_template('kiosk/input_pick.html', picker=picker,
                           pick_type_id=pick_type_id, **ctx)


@main_bp.route('/kiosk/<branch>/complete/<int:pick_id>', methods=['POST'])
def kiosk_complete_pick(branch, pick_id):
    _kiosk_context(branch)  # validate branch
    pick = Pick.query.get_or_404(pick_id)
    now = datetime.utcnow()
    pick.completed_time = now
    audit = AuditEvent(
        event_type='pick_completed',
        entity_type='pick',
        entity_id=pick.id,
        so_number=pick.barcode_number,
        occurred_at=now,
    )
    db.session.add(audit)
    db.session.commit()
    flash('Pick completed successfully.')
    return redirect(url_for('main.kiosk_pickers', branch=branch))


@main_bp.route('/kiosk/<branch>/work-orders')
def kiosk_work_orders(branch):
    ctx = _kiosk_context(branch)
    normalized = ctx['kiosk_branch']
    pickers = Pickster.query.filter(
        Pickster.user_type == 'door_builder',
        (Pickster.branch_code == normalized) | (Pickster.branch_code == None),
    ).order_by(Pickster.name).all()
    return render_template('kiosk/wo_user_selection.html', pickers=pickers, **ctx)


@main_bp.route('/kiosk/<branch>/work-orders/open/<int:user_id>')
def kiosk_work_orders_open(branch, user_id):
    ctx = _kiosk_context(branch)
    user = Pickster.query.get_or_404(user_id)
    open_orders = WorkOrderAssignment.query.filter(
        WorkOrderAssignment.assigned_to_id == user.id,
        WorkOrderAssignment.status.in_(['Open', 'Assigned']),
    ).order_by(WorkOrderAssignment.created_at.desc()).all()
    return render_template('kiosk/wo_open_orders.html', user=user,
                           open_orders=open_orders, **ctx)


@main_bp.route('/kiosk/<branch>/work-orders/scan/<int:user_id>')
def kiosk_work_order_scan(branch, user_id):
    ctx = _kiosk_context(branch)
    user = Pickster.query.get_or_404(user_id)
    return render_template('kiosk/wo_scan_barcode.html', user=user, **ctx)


@main_bp.route('/kiosk/<branch>/work-orders/select')
def kiosk_work_order_select(branch):
    ctx = _kiosk_context(branch)
    user_id = request.args.get('user_id')
    barcode = (request.args.get('barcode') or '').strip()
    if not user_id or not barcode:
        flash('A user and sales order barcode are required.', 'warning')
        return redirect(url_for('main.kiosk_work_orders', branch=branch))
    user = Pickster.query.get_or_404(user_id)
    erp = ERPService()
    items = erp.get_work_orders_by_barcode(barcode)
    return render_template('kiosk/wo_select_orders.html', user=user,
                           barcode=barcode, items=items, **ctx)


@main_bp.route('/kiosk/<branch>/work-orders/complete/<int:wo_id>', methods=['POST'])
def kiosk_complete_work_order(branch, wo_id):
    _kiosk_context(branch)  # validate branch
    wo = WorkOrderAssignment.query.get_or_404(wo_id)
    now = datetime.utcnow()
    wo.status = 'Complete'
    wo.completed_at = now
    wo.completed_by_id = wo.assigned_to_id
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
    return redirect(url_for('main.kiosk_work_orders_open', branch=branch, user_id=wo.assigned_to_id))


@main_bp.route('/kiosk/<branch>/work-orders/start', methods=['POST'])
def kiosk_start_work_orders(branch):
    ctx = _kiosk_context(branch)
    user_id = request.form.get('user_id', type=int)
    selected_items = request.form.getlist('selected_items')

    if not user_id:
        flash('A builder selection is required.', 'danger')
        return redirect(url_for('main.kiosk_work_orders', branch=branch))
    if not selected_items:
        flash('Select at least one work order to start.', 'warning')
        return redirect(url_for('main.kiosk_work_order_scan', branch=branch, user_id=user_id))

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
            created_at=datetime.utcnow(),
            branch_code=ctx['kiosk_branch'],
        )
        db.session.add(new_wo)
        created += 1

    db.session.commit()
    message = f'{created} work order(s) queued for the builder.'
    if skipped:
        message += f' Skipped {skipped} invalid selection(s).'
    flash(message, 'success' if created else 'warning')
    return redirect(url_for('main.kiosk_work_orders_open', branch=branch, user_id=user_id))

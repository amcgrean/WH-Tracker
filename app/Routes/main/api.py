import os
import re
import json
from datetime import datetime, timedelta
from flask import request, url_for, jsonify
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.Models.models import Pickster, Pick, PickAssignment, AuditEvent, ERPSyncState
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import (
    WILL_CALL_TYPE_ID, _get_branch,
    ensure_pick_type_exists, get_pick_type_name, pick_type_from_handling_code,
    localize_to_cst, calculate_business_elapsed_time, format_elapsed_time,
)


@main_bp.route('/api/smart_scan', methods=['POST'])
def api_smart_scan():
    """
    Smart scan endpoint: auto-detects pick type from ERP sale_type.

    Decision flow:
    1. If an incomplete Pick exists with this barcode -> complete it
    2. If ERP sale_type is WILLCALL -> create auto-completed will call pick
    3. Otherwise -> create a new timed pick (regular)
    4. If barcode not found in ERP -> fallback to regular pick

    NOTE: This JSON endpoint does not carry CSRF protection.  If a
    CSRF middleware (e.g. Flask-WTF CSRFProtect) is enabled app-wide,
    either exempt this route or require the X-CSRFToken header from
    the client-side fetch call.
    """
    data = request.get_json(silent=True) or {}
    picker_id = data.get('picker_id')
    raw_barcode = (data.get('barcode') or '').strip()

    if not picker_id or not raw_barcode:
        return jsonify({'error': 'picker_id and barcode are required'}), 400

    picker = Pickster.query.get(picker_id)
    if not picker:
        return jsonify({'error': 'Picker not found'}), 404

    # Validate barcode format: digits, spaces, hyphens only; max 50 chars
    if not re.match(r'^[0-9\s\-]+$', raw_barcode) or len(raw_barcode) > 50:
        return jsonify({'error': 'Invalid barcode format'}), 400

    # Parse barcode: "SO_NUMBER-SHIPMENT_SEQ" (e.g., "0001463004-001")
    shipment_num = None
    if '-' in raw_barcode:
        parts = raw_barcode.split('-', 1)
        barcode = parts[0].strip()
        shipment_num = parts[1].strip() or None
    else:
        barcode = raw_barcode.replace(' ', '')

    now = datetime.utcnow()

    # 1. Check for existing incomplete pick with this barcode (scoped to picker's branch)
    incomplete_q = Pick.query.filter_by(barcode_number=barcode, completed_time=None)
    if picker.branch_code:
        incomplete_q = incomplete_q.filter_by(branch_code=picker.branch_code)
    existing_pick = incomplete_q.first()

    if existing_pick:
        existing_pick.completed_time = now
        audit = AuditEvent(
            event_type='pick_completed',
            entity_type='pick',
            entity_id=existing_pick.id,
            so_number=barcode,
            actor_id=picker.id,
            occurred_at=now,
        )
        db.session.add(audit)
        db.session.commit()
        return jsonify({
            'action': 'completed',
            'pick_id': existing_pick.id,
            'pick_type': get_pick_type_name(existing_pick.pick_type_id),
            'so_number': barcode,
            'message': f'Pick {barcode} completed.',
        })

    # 2. Look up sale_type and handling_code from ERP to determine pick type
    sale_type = None
    handling_code = None
    try:
        erp = ERPService()
        sale_type = erp.get_so_sale_type(barcode)
        if not (sale_type and sale_type.upper() == 'WILLCALL'):
            handling_code = erp.get_so_primary_handling_code(barcode)
    except Exception:
        pass  # ERP lookup failure -> fallback to regular pick

    if sale_type and sale_type.upper() == 'WILLCALL':
        # Will call: auto-complete immediately
        pick_type_id = WILL_CALL_TYPE_ID
        completed_time = now
        action = 'will_call_completed'
        message = f'Will Call {barcode} recorded.'
    else:
        # Map handling_code to pick type; defaults to Yard (1)
        pick_type_id = pick_type_from_handling_code(handling_code)
        completed_time = None
        action = 'started'
        pick_type_name = get_pick_type_name(pick_type_id)
        message = f'Pick {barcode} started ({pick_type_name}).'

    ensure_pick_type_exists(pick_type_id)

    new_pick = Pick(
        barcode_number=barcode,
        shipment_num=shipment_num,
        start_time=now,
        completed_time=completed_time,
        picker_id=picker.id,
        pick_type_id=pick_type_id,
        branch_code=picker.branch_code,
    )
    db.session.add(new_pick)
    db.session.flush()

    event_type = 'pick_completed' if completed_time else 'pick_started'
    audit = AuditEvent(
        event_type=event_type,
        entity_type='pick',
        entity_id=new_pick.id,
        so_number=barcode,
        actor_id=picker.id,
        occurred_at=now,
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({
        'action': action,
        'pick_id': new_pick.id,
        'pick_type': get_pick_type_name(pick_type_id),
        'so_number': barcode,
        'message': message,
    })


@main_bp.route('/api/pickers_picks')
def api_pickers_picks():
    today = datetime.now().date()
    five_days_ago = today - timedelta(days=5)

    # Count of all completed picks today excluding will call picks
    today_count = Pick.query.filter(
        func.date(Pick.completed_time) == today,
        Pick.pick_type_id != WILL_CALL_TYPE_ID
    ).count()

    # Count for will call tickets today
    will_call_count = Pick.query.filter(
        func.date(Pick.completed_time) == today,
        Pick.pick_type_id == WILL_CALL_TYPE_ID
    ).count()

    # Average count of completed picks over the last 5 days excluding will call picks
    recent_counts = db.session.query(
        func.date(Pick.completed_time), func.count('*').label('daily_count')
    ).filter(
        func.date(Pick.completed_time) >= five_days_ago,
        func.date(Pick.completed_time) < today,
        Pick.pick_type_id != WILL_CALL_TYPE_ID
    ).group_by(
        func.date(Pick.completed_time)
    ).all()

    average_count = sum(count for _, count in recent_counts) / len(recent_counts) if recent_counts else 0

    data = []
    pickers = Pickster.query.order_by(Pickster.name).all()
    for picker in pickers:
        open_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None)\
                               .order_by(Pick.start_time.asc()).all()  # Sorting by start time

        for pick in open_picks:
            start_time_localized = localize_to_cst(pick.start_time)
            data.append({
                'barcode_number': pick.barcode_number,
                'shipment_num': pick.shipment_num,
                'order_url': url_for('main.pick_detail', so_number=pick.barcode_number),
                'start_time': start_time_localized.strftime('%Y-%m-%d %I:%M %p %Z'),
                'elapsed_time': format_elapsed_time(start_time_localized),
                'picker_name': picker.name,
                'pick_type': get_pick_type_name(pick.pick_type_id)
            })

    return jsonify({
        "picks": data,
        "today_count": today_count,
        "will_call_count": will_call_count,
        "average_count": average_count
    })


@main_bp.route('/api/picks')
def api_picks():
    data = []
    picker_id = request.args.get('picker_id')

    if picker_id:
        picker = Pickster.query.get(picker_id)
        if not picker:
            return jsonify({'error': 'Picker not found'}), 404
        pickers = [picker]
    else:
        pickers = Pickster.query.order_by(Pickster.name).all()

    for picker in pickers:
        open_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None)\
                               .order_by(Pick.id.asc()).all()  # Sorting by ID

        picks_data = [{
            'barcode_number': pick.barcode_number,
            'shipment_num': pick.shipment_num,
            'order_url': url_for('main.pick_detail', so_number=pick.barcode_number),
            'start_time': localize_to_cst(pick.start_time).strftime('%Y-%m-%d %I:%M %p %Z'),
            'elapsed_time': calculate_business_elapsed_time(pick.start_time),
            'picker_name': picker.name,
            'pick_type': get_pick_type_name(pick.pick_type_id)
        } for pick in open_picks]

        data.extend(picks_data)

    return jsonify(data)


@main_bp.route('/api/confirm_staged/<so_number>', methods=['POST'])
def confirm_staged(so_number):
    """
    Locally confirm that a Sales Order has been staged/loaded onto the truck.
    Persists the confirmation as an AuditEvent (app-owned table).
    """
    so_number = so_number.strip()
    if not so_number:
        return jsonify({'error': 'SO number is required'}), 400

    erp = ERPService()
    if not erp.get_so_header(so_number):
        return jsonify({'error': f'Order {so_number} was not found'}), 404

    now = datetime.utcnow()

    audit = AuditEvent(
        event_type='staged_confirmed',
        entity_type='sales_order',
        so_number=so_number,
        notes=request.json.get('notes') if request.is_json else None,
        occurred_at=now,
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({'status': 'ok', 'so_number': so_number, 'staged_at': now.isoformat()})


@main_bp.route('/api/sync/status')
def api_sync_status():
    state = ERPSyncState.query.order_by(ERPSyncState.last_heartbeat_at.desc()).first()
    if not state:
        return jsonify({
            'ok': False,
            'status': 'missing',
            'message': 'No ERP sync worker heartbeat has been recorded yet.',
        }), 404

    counts = {}
    if state.last_counts_json:
        try:
            counts = json.loads(state.last_counts_json)
        except Exception:
            counts = {}

    age_seconds = None
    if state.last_heartbeat_at:
        age_seconds = int((datetime.utcnow() - state.last_heartbeat_at).total_seconds())

    stale_threshold = max(15, int(state.interval_seconds or 5) * 3)
    healthy = state.last_status in ('success', 'noop') and (age_seconds is None or age_seconds <= stale_threshold)

    return jsonify({
        'ok': healthy,
        'worker_name': state.worker_name,
        'worker_mode': state.worker_mode,
        'source_mode': state.source_mode,
        'target_mode': state.target_mode,
        'status': state.last_status,
        'interval_seconds': state.interval_seconds,
        'change_monitoring': state.change_monitoring,
        'last_heartbeat_at': state.last_heartbeat_at.isoformat() + 'Z' if state.last_heartbeat_at else None,
        'last_success_at': state.last_success_at.isoformat() + 'Z' if state.last_success_at else None,
        'last_error_at': state.last_error_at.isoformat() + 'Z' if state.last_error_at else None,
        'last_error': state.last_error,
        'last_change_token': state.last_change_token,
        'last_push_reason': state.last_push_reason,
        'age_seconds': age_seconds,
        'counts': counts,
    })


@main_bp.route('/api/geocode-pending', methods=['POST'])
def api_geocode_pending():
    """Deprecated: geocoding now occurs in beisser-api mirror sync, not WH-Tracker."""
    return jsonify({
        'error': 'deprecated',
        'message': 'Ship-to geocoding is managed upstream by beisser-api; WH-Tracker now consumes mirror lat/lon only.',
    }), 410


@main_bp.route('/debug/counts')
def debug_counts():
    try:
        erp = ERPService()
        raw_summary = erp.get_open_so_summary()
        open_work_orders = erp.get_open_work_orders()

        return jsonify({
            'open_sales_orders': len(raw_summary),
            'open_work_orders': len(open_work_orders),
            'erp_cloud_mode': erp.cloud_mode,
            'summary_length': len(raw_summary),
            'db_uri': str(db.engine.url).split('@')[1] if '@' in str(db.engine.url) else 'local',
            'cloud_mode_env': str(os.environ.get('CLOUD_MODE')).lower() == 'true'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@main_bp.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    period = request.args.get('period', default='today')

    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())  # Monday as the first day
    start_of_month = today.replace(day=1)  # First day of the current month

    def get_counts(start_date, end_date):
        query_end_date = end_date + timedelta(days=1)
        completed_picks = Pick.query.filter(
            Pick.completed_time.between(start_date, query_end_date)
        ).count()
        will_calls = Pick.query.filter(
            Pick.completed_time.between(start_date, query_end_date),
            Pick.pick_type_id == WILL_CALL_TYPE_ID
        ).count()
        return completed_picks, will_calls

    # Gather counts
    if period == 'today':
        start_date = today
        end_date = today
    elif period == 'week':
        start_date = start_of_week
        end_date = today
    elif period == 'month':
        start_date = start_of_month
        end_date = today
    else:
        return jsonify({'error': 'Invalid period'}), 400

    today_picks, today_will_calls = get_counts(start_date, end_date)
    week_picks, week_will_calls = get_counts(start_of_week, today)
    month_picks, month_will_calls = get_counts(start_of_month, today)

    # Gather completed picks for the period
    completed_picks = Pick.query.join(Pickster).options(
        db.joinedload(Pick.pickster)
    ).filter(
        func.date(Pick.completed_time).between(start_date, end_date + timedelta(days=1))
    ).order_by(Pickster.name).all()

    completed_picks_data = [{
        'picker_name': pick.pickster.name,
        'barcode_number': pick.barcode_number,
        'pick_type': get_pick_type_name(pick.pick_type_id),
        'start_time': localize_to_cst(pick.start_time).strftime('%Y-%m-%d %I:%M %p %Z'),
        'complete_time': localize_to_cst(pick.completed_time).strftime('%Y-%m-%d %I:%M %p %Z')
    } for pick in completed_picks]

    return jsonify({
        'todayStats': {'picks': today_picks, 'willCalls': today_will_calls},
        'weekStats': {'picks': week_picks, 'willCalls': week_will_calls},
        'monthStats': {'picks': month_picks, 'willCalls': month_will_calls},
        'completedPicks': completed_picks_data
    })


@main_bp.route('/api/board/orders')
def api_board_orders():
    """JSON endpoint for the order board — lightweight alternative to the full HTML render."""
    erp = ERPService()
    order_summary = erp.get_open_order_board_summary(branch=_get_branch())

    so_numbers = [item['so_number'] for item in order_summary]
    assignments = {
        a.so_number: a.picker_id
        for a in PickAssignment.query.filter(PickAssignment.so_number.in_(so_numbers)).all()
    } if so_numbers else {}
    picker_ids = [pid for pid in assignments.values() if pid]
    picker_map = {
        p.id: p.name
        for p in Pickster.query.filter(
            Pickster.user_type == 'picker',
            Pickster.id.in_(picker_ids),
        ).all()
    } if picker_ids else {}

    for item in order_summary:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = picker_map.get(picker_id) if picker_id else None

    return jsonify(order_summary)

import os
import re
import hmac
import logging
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.Models.models import Pickster, Pick, PickTypes, AuditEvent, POSubmission
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import (
    WILL_CALL_TYPE_ID, DEFAULT_PICK_TYPES, HANDLING_CODE_TO_PICK_TYPE,
    ensure_pick_type_exists, get_pick_type_name, pick_type_from_handling_code,
    localize_to_cst, calculate_business_elapsed_time, format_elapsed_time,
)

logger = logging.getLogger(__name__)


def _build_homepage_data(roles, rep_id, branch):
    """Build role-appropriate dashboard data for the homepage."""
    data = {'roles_active': []}
    roles = set(roles or [])
    erp = None

    def _get_erp():
        nonlocal erp
        if erp is None:
            erp = ERPService()
        return erp

    today = datetime.utcnow().date()

    # ── Sales ──
    if roles & {'sales', 'admin', 'ops'}:
        try:
            metrics = _get_erp().get_sales_hub_metrics(rep_id=rep_id or '')
            data['sales'] = {
                'open_orders': metrics.get('open_orders_count', 0),
                'shipping_today': metrics.get('total_orders_today', 0),
            }
        except Exception:
            logger.exception("Homepage: failed to load sales metrics")
            data['sales'] = {'open_orders': None, 'shipping_today': None}
        if 'sales' in roles:
            data['roles_active'].append('sales')

    # ── Warehouse / Picker ──
    if roles & {'warehouse', 'picker', 'admin', 'ops', 'supervisor'}:
        try:
            open_picks = _get_erp().get_open_picks()
            handling_counts = {}
            for p in open_picks:
                code = str(p.get('handling_code', '') or '').strip().upper() or '—'
                handling_counts[code] = handling_counts.get(code, 0) + 1
            data['warehouse'] = {
                'open_picks': len(open_picks),
                'handling_breakdown': dict(sorted(handling_counts.items())),
            }
        except Exception:
            logger.exception("Homepage: failed to load warehouse metrics")
            data['warehouse'] = {'open_picks': None, 'handling_breakdown': {}}

        # Today's completed picks from local DB
        try:
            data['warehouse']['picks_completed_today'] = Pick.query.filter(
                func.date(Pick.completed_time) == today
            ).count()
        except Exception:
            data['warehouse']['picks_completed_today'] = None

        if roles & {'warehouse', 'picker'}:
            data['roles_active'].append('warehouse')

    # ── Supervisor ──
    if roles & {'supervisor', 'admin', 'ops'}:
        try:
            total_pickers = Pickster.query.filter(
                (Pickster.user_type == 'picker') | (Pickster.user_type.is_(None))
            ).count()
            active_count = db.session.query(
                func.count(func.distinct(Pick.picker_id))
            ).join(Pickster, Pick.picker_id == Pickster.id).filter(
                (Pickster.user_type == 'picker') | (Pickster.user_type.is_(None)),
                Pick.completed_time.is_(None),
            ).scalar() or 0
            data['supervisor'] = {
                'total_pickers': total_pickers,
                'active_pickers': active_count,
                'idle_pickers': total_pickers - active_count,
            }
        except Exception:
            logger.exception("Homepage: failed to load supervisor metrics")
            data['supervisor'] = {
                'total_pickers': None, 'active_pickers': None, 'idle_pickers': None,
            }
        if 'supervisor' in roles:
            data['roles_active'].append('supervisor')

    # ── Work Orders (supervisor, ops, admin) ──
    if roles & {'supervisor', 'admin', 'ops'}:
        try:
            wos = _get_erp().get_open_work_orders()
            data['work_orders'] = {'open_count': len(wos)}
        except Exception:
            logger.exception("Homepage: failed to load work order metrics")
            data['work_orders'] = {'open_count': None}

    # ── Dispatch / Delivery ──
    if roles & {'dispatch', 'delivery', 'admin', 'ops'}:
        try:
            deliveries = _get_erp().get_sales_delivery_tracker(branch_id=branch)
            data['dispatch'] = {'todays_deliveries': len(deliveries)}
        except Exception:
            logger.exception("Homepage: failed to load dispatch metrics")
            data['dispatch'] = {'todays_deliveries': None}
        if roles & {'dispatch', 'delivery'}:
            data['roles_active'].append('dispatch')

    # ── Ops / Admin ──
    if roles & {'admin', 'ops'}:
        data['roles_active'].append('ops')

    # ── Purchasing ──
    if roles & {'purchasing', 'admin', 'ops'}:
        try:
            pending_reviews = POSubmission.query.filter(
                POSubmission.status == 'pending'
            ).count()
            data['purchasing'] = {'pending_reviews': pending_reviews}
        except Exception:
            logger.exception("Homepage: failed to load purchasing metrics")
            data['purchasing'] = {'pending_reviews': None}
        if 'purchasing' in roles:
            data['roles_active'].append('purchasing')

    return data


@main_bp.route('/')
def work_center():
    roles = session.get('user_roles', [])
    rep_id = session.get('user_rep_id', '')
    branch = session.get('selected_branch') or None
    homepage_data = _build_homepage_data(roles, rep_id, branch)
    return render_template('workcenter.html', data=homepage_data)


@main_bp.route('/pick_tracker')
def index():
    # Filter for pickers only (or show all if type is NULL for backward compat)
    pickers = Pickster.query.filter(
        (Pickster.user_type == 'picker') | (Pickster.user_type == None)
    ).order_by(Pickster.name).all()
    return render_template('index.html', pickers=pickers)


#####PICKER ADMIN STUFF#####
@main_bp.route('/admin')
def admin():
    # Example admin page that might show all pickers for management
    pickers = Pickster.query.all()
    return render_template('admin.html', pickers=pickers)


@main_bp.route('/add_picker', methods=['POST'])
def add_picker():
    picker_name = request.form['picker_name']
    user_type = request.form.get('user_type', 'picker')
    if picker_name:
        try:
            picker = Pickster(name=picker_name, user_type=user_type)  # Use the correct class name
            db.session.add(picker)
            db.session.commit()
            flash('Picker added successfully.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash(f'A picker named "{picker_name}" already exists.', 'error')
    else:
        flash('Please enter a picker name.', 'error')
    return redirect(url_for('main.admin'))


@main_bp.route('/edit_picker/<int:picker_id>', methods=['GET', 'POST'])
def edit_picker(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    if request.method == 'POST':
        new_name = request.form['picker_name']
        new_type = request.form.get('user_type')
        if new_name:
            try:
                picker.name = new_name
                if new_type:
                    picker.user_type = new_type
                db.session.commit()
                flash('Picker name updated successfully.', 'success')
                return redirect(url_for('main.admin'))
            except IntegrityError:
                db.session.rollback()
                flash(f'A picker named "{new_name}" already exists.', 'error')
    return render_template('edit_picker.html', picker=picker)


@main_bp.route('/delete_picker/<int:picker_id>', methods=['POST'])
def delete_picker(picker_id):
    admin_password = os.environ.get('ADMIN_DELETE_PASSWORD', '')
    submitted = request.form.get('password', '')
    # Require the env var to be set and use constant-time comparison to prevent timing attacks
    if not admin_password or not hmac.compare_digest(admin_password, submitted):
        flash('Incorrect password.', 'error')
        return redirect(url_for('main.admin'))
    picker = Pickster.query.get_or_404(picker_id)
    db.session.delete(picker)
    db.session.commit()
    flash('Picker deleted successfully.', 'success')
    return redirect(url_for('main.admin'))


###INPUT PICK AND COMPLETE TRACKING#####
@main_bp.route('/confirm_picker/<int:picker_id>', methods=['GET', 'POST'])
def confirm_picker(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    incomplete_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None).all()

    # Directly render the template with incomplete picks, if any
    # The POST method behavior needs to be adjusted based on your form handling
    return render_template('complete_pick.html', picker=picker, incomplete_picks=incomplete_picks, pick_type_names=DEFAULT_PICK_TYPES)


@main_bp.route('/input_pick/<int:picker_id>/<int:pick_type_id>', methods=['GET', 'POST'])
def input_pick(picker_id, pick_type_id):
    picker = Pickster.query.get_or_404(picker_id)

    if not ensure_pick_type_exists(pick_type_id):
        flash('Invalid pick type selected.', 'error')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        raw_barcode = (request.form.get('barcode') or '').strip()
        if not raw_barcode:
            flash('Barcode is required.', 'error')
            return render_template('input_pick.html', picker=picker, pick_type_id=pick_type_id)

        if not re.match(r'^[0-9\s\-]+$', raw_barcode) or len(raw_barcode) > 50:
            flash('Invalid barcode format.', 'error')
            return render_template('input_pick.html', picker=picker, pick_type_id=pick_type_id)

        # Parse barcode: format may be "SO_NUMBER-SHIPMENT_SEQ" (e.g. "0001463004-001")
        shipment_num = None
        if '-' in raw_barcode:
            parts = raw_barcode.split('-', 1)
            barcode = parts[0].strip()
            shipment_num = parts[1].strip() or None
        else:
            barcode = raw_barcode.replace(' ', '')

        start_time = datetime.utcnow()
        completed_time = start_time if pick_type_id == WILL_CALL_TYPE_ID else None

        new_pick = Pick(
            barcode_number=barcode,
            shipment_num=shipment_num,
            start_time=start_time,
            picker_id=picker.id,
            pick_type_id=pick_type_id,
            completed_time=completed_time,
            branch_code=picker.branch_code,
        )
        db.session.add(new_pick)

        # Audit trail
        event_type = 'pick_completed' if completed_time else 'pick_started'
        db.session.flush()
        audit = AuditEvent(
            event_type=event_type,
            entity_type='pick',
            entity_id=new_pick.id,
            so_number=barcode,
            actor_id=picker.id,
            occurred_at=start_time,
        )
        db.session.add(audit)
        db.session.commit()

        if completed_time:
            flash(f'Will Call {barcode} recorded.')
        else:
            flash('Pick started successfully.')
        return redirect(url_for('main.index'))
    return render_template('input_pick.html', picker=picker, pick_type_id=pick_type_id)


@main_bp.route('/complete_pick/<int:pick_id>', methods=['GET', 'POST'])
def complete_pick(pick_id):
    pick = Pick.query.get_or_404(pick_id)

    if request.method == 'POST':
        now = datetime.utcnow()
        pick.completed_time = now

        # Audit trail
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
        return redirect(url_for('main.index'))
    else:
        picker = Pickster.query.get_or_404(pick.picker_id)
        incomplete_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None).all()
        return render_template('complete_pick.html', picker=picker, incomplete_picks=incomplete_picks, pick_type_names=DEFAULT_PICK_TYPES)


@main_bp.route('/start_pick/<int:picker_id>/<int:pick_type_id>', methods=['POST'])
def start_pick(picker_id, pick_type_id):
    picker = Pickster.query.get_or_404(picker_id)

    if not ensure_pick_type_exists(pick_type_id):
        flash('Invalid pick type selected.', 'error')
        return redirect(url_for('main.index'))

    raw_barcode = request.form.get('barcode', '').strip()
    if not raw_barcode:
        flash('Barcode is required.', 'error')
        return redirect(url_for('main.index'))
    # Allow digits, spaces, and hyphens (matching frontend validation)
    if not re.match(r'^[0-9\s\-]+$', raw_barcode) or len(raw_barcode) > 50:
        flash('Invalid barcode format.', 'error')
        return redirect(url_for('main.index'))

    # Parse barcode: format may be "SO_NUMBER-SHIPMENT_SEQ" (e.g. "0001463004-001")
    # The suffix after the hyphen is the shipment sequence from erp_mirror_shipments_header
    shipment_num = None
    if '-' in raw_barcode:
        parts = raw_barcode.split('-', 1)
        barcode = parts[0].strip()
        shipment_num = parts[1].strip() or None
    else:
        barcode = raw_barcode.replace(' ', '')

    start_time = datetime.utcnow()
    completed_time = start_time if pick_type_id == WILL_CALL_TYPE_ID else None

    new_pick = Pick(
        barcode_number=barcode,
        shipment_num=shipment_num,
        start_time=start_time,
        completed_time=completed_time,
        picker_id=picker.id,
        pick_type_id=pick_type_id,
        branch_code=picker.branch_code,
    )
    db.session.add(new_pick)

    # Audit trail
    event_type = 'pick_completed' if completed_time else 'pick_started'
    db.session.flush()  # get new_pick.id before commit
    audit = AuditEvent(
        event_type=event_type,
        entity_type='pick',
        entity_id=new_pick.id,
        so_number=barcode,
        actor_id=picker.id,
        occurred_at=start_time,
    )
    db.session.add(audit)
    db.session.commit()

    if completed_time:
        flash(f'Will Call {barcode} recorded.')
    else:
        flash('Pick started successfully.')
    return redirect(url_for('main.index'))


@main_bp.route('/pickers_picks')
def pickers_picks():
    today = datetime.now().date()  ###new insert 7.9.24 2pm
    five_days_ago = today - timedelta(days=5)

    # Count of completed picks today excluding will call picks
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

    # Calculate average
    if recent_counts:
        average_count = sum(count for _, count in recent_counts) / len(recent_counts)
    else:
        average_count = 0

    return render_template('pickers_picks.html', today_count=today_count, will_call_count=will_call_count, average_count=average_count)


@main_bp.route('/picker_stats', methods=['GET'])
def picker_stats():
    sort_by = request.args.get('sort', 'id')
    order = request.args.get('order', 'asc')
    period = request.args.get('period', 'custom')

    today = datetime.now().date()
    if period == '7days':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == '30days':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'ytd':
        start_date = datetime(today.year, 1, 1)
        end_date = today
    else:
        start_date_str = request.args.get('start_date', (today - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    query_end_date = end_date + timedelta(days=1)

    query_end_date = end_date + timedelta(days=1)

    # 1. Overall Stats
    total_picks = Pick.query.filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).count()

    # SQLite compatible time difference in seconds
    time_diff_expr = func.strftime('%s', Pick.completed_time) - func.strftime('%s', Pick.start_time)

    avg_time = db.session.query(func.avg(time_diff_expr)).filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).scalar()

    avg_time_minutes = round(avg_time / 60, 2) if avg_time else 0

    # 2. Stats by Pick Type (Dynamic)
    type_stats_query = db.session.query(
        PickTypes.type_name,
        func.count(Pick.id).label('count'),
        func.avg(time_diff_expr).label('avg_seconds')
    ).join(Pick, Pick.pick_type_id == PickTypes.pick_type_id)\
     .filter(Pick.completed_time >= start_date, Pick.completed_time < query_end_date)\
     .group_by(PickTypes.type_name)\
     .all()

    type_stats = []
    for t in type_stats_query:
        type_stats.append({
            'name': t.type_name,
            'count': t.count,
            'avg_time': round(t.avg_seconds / 60, 2) if t.avg_seconds else 0
        })

    # 3. Top Pickers
    top_pickers = db.session.query(
        Pickster.name,
        func.count(Pick.id).label('pick_count')
    ).join(Pick).filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).group_by(Pickster.name).order_by(func.count(Pick.id).desc()).limit(5).all()

    # 4. Detailed Table Data — capped at 2000 rows to prevent timeout on large date ranges
    picks = Pick.query.options(joinedload(Pick.pickster)).filter(
        Pick.start_time >= start_date,
        Pick.completed_time < query_end_date,
        Pick.completed_time.isnot(None)
    ).order_by(Pick.completed_time.desc()).limit(2000).all()

    picker_stats_map = {}
    for pick in picks:
        pid = pick.picker_id
        if pid not in picker_stats_map:
            picker_stats_map[pid] = {
                'id': pid,
                'name': pick.pickster.name,
                'yard_picks': 0,
                'will_call_picks': 0,
                'total_time': timedelta(),
                'count': 0
            }

        if pick.pick_type_id == 1:
            picker_stats_map[pid]['yard_picks'] += 1
        elif pick.pick_type_id == WILL_CALL_TYPE_ID:
            picker_stats_map[pid]['will_call_picks'] += 1

        elapsed_time = pick.completed_time - pick.start_time
        picker_stats_map[pid]['total_time'] += elapsed_time
        picker_stats_map[pid]['count'] += 1

    stats_list = []
    for pid, stats in picker_stats_map.items():
        average_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else timedelta()
        hours, remainder = divmod(average_time.total_seconds(), 3600)
        minutes = remainder // 60
        avg_picks_per_day = stats['count'] / ((end_date - start_date).days or 1)

        stats_list.append({
            'id': stats['id'],
            'name': stats['name'],
            'yard_picks': stats['yard_picks'],
            'will_call_picks': stats['will_call_picks'],
            'avg_pick_time': f"{int(hours)}:{int(minutes):02d}",
            'avg_picks_per_day': round(avg_picks_per_day, 2)
        })

    return render_template(
        'picker_stats.html',
        stats=stats_list,
        type_stats=type_stats,
        total_picks=total_picks,
        avg_time=avg_time_minutes,
        top_pickers=top_pickers,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        order=order,
        period=period
    )


@main_bp.route('/picker_details/<int:picker_id>')
def picker_details(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    picks = Pick.query.filter_by(picker_id=picker_id).order_by(Pick.start_time.desc()).all()

    # Enrich picks with ERP data
    so_numbers = [p.barcode_number for p in picks]
    erp = ERPService()
    hist_data = erp.get_historical_so_summary(so_numbers=so_numbers) if so_numbers else []
    erp_map = {item['so_number']: item for item in hist_data}

    # Convert and format the pick times
    updated_picks = []
    for pick in picks:
        start_time_cst = localize_to_cst(pick.start_time)
        time_to_complete = "In progress"
        if pick.completed_time:
            time_to_complete = format_elapsed_time(pick.start_time, pick.completed_time)

        erp_info = erp_map.get(pick.barcode_number, {})

        updated_picks.append({
            'barcode_number': pick.barcode_number,
            'shipment_num': pick.shipment_num,
            'order_url': url_for('main.pick_detail', so_number=pick.barcode_number),
            'customer_name': erp_info.get('customer_name', 'Unknown'),
            'reference': erp_info.get('reference', ''),
            'start_time': start_time_cst.strftime('%Y-%m-%d %I:%M %p %Z'),
            'time_to_complete': time_to_complete
        })

    return render_template('picker_details.html', picker=picker, picks=updated_picks)


@main_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

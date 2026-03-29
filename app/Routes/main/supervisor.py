import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, current_app

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.Models.models import Pickster, Pick, WorkOrderAssignment, PickAssignment, AuditEvent
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import CHUNK_SIZE


@main_bp.route('/supervisor/dashboard')
def supervisor_dashboard():
    local_data_unavailable = False
    try:
        pickers = Pickster.query.all()

        # 2. Get active assignments (who is assigned to what)
        pick_assignments = {a.picker_id: a.so_number for a in PickAssignment.query.all()}
        wo_assignments = {
            a.assigned_to_id: a.wo_id
            for a in WorkOrderAssignment.query.filter(
                WorkOrderAssignment.assigned_to_id != None,
                WorkOrderAssignment.completed_at == None,
            ).all()
        }

        # 3. Get currently Active Picks (Started but not Completed)
        active_picks = Pick.query.options(joinedload(Pick.pickster)).filter(Pick.completed_time == None).all()
        active_map = {p.picker_id: p for p in active_picks}
        recent_picks = Pick.query.options(joinedload(Pick.pickster)).filter(
            Pick.completed_time != None
        ).order_by(Pick.completed_time.desc()).limit(10).all()
    except SQLAlchemyError:
        current_app.logger.exception("Supervisor dashboard local DB query failed")
        flash('Supervisor live assignment data is temporarily unavailable.', 'warning')
        local_data_unavailable = True
        pickers = []
        pick_assignments = {}
        wo_assignments = {}
        active_map = {}
        recent_picks = []

    picker_data = []
    for p in pickers:
        p_info = {
            'name': p.name,
            'user_type': p.user_type,
            'status': 'idle',
            'current_task': None,
            'task_type': None,
            'active_duration': 0
        }

        # 1. Check Active Picks (Live "Doing")
        if p.id in active_map:
            pick = active_map[p.id]
            p_info['status'] = 'active'
            p_info['current_task'] = pick.barcode_number
            p_info['task_type'] = 'Pick'
            if pick.start_time:
                duration = (datetime.utcnow() - pick.start_time).total_seconds() / 60
                p_info['active_duration'] = max(0, int(duration))

        # 2. Check Pick Assignments (Planned)
        elif p.id in pick_assignments:
            p_info['status'] = 'assigned'
            p_info['current_task'] = pick_assignments[p.id]
            p_info['task_type'] = 'Pick'

        # 3. Check Work Order Assignments (Production)
        elif p.id in wo_assignments:
            p_info['status'] = 'assigned'
            p_info['current_task'] = wo_assignments[p.id]
            p_info['task_type'] = 'Production (WO)'

        picker_data.append(p_info)

    # Enrich recent picks with ERP data
    recent_so_numbers = [p.barcode_number for p in recent_picks]
    erp = ERPService()
    hist_data = []
    if recent_so_numbers:
        try:
            hist_data = erp.get_historical_so_summary(so_numbers=recent_so_numbers)
        except Exception:
            current_app.logger.exception("Supervisor dashboard ERP enrichment failed")
    erp_map = {str(item.get('so_number')): item for item in hist_data if item.get('so_number')}

    return render_template('supervisor/dashboard.html',
                          pickers=picker_data,
                          recent_picks=recent_picks,
                          erp_map=erp_map,
                          local_data_unavailable=local_data_unavailable,
                          now=datetime.utcnow())


@main_bp.route('/supervisor/work_orders')
def supervisor_work_orders():
    erp = ERPService()
    erp_wos = erp.get_open_work_orders()

    # Fetch local assignments for these WOs in chunks to avoid large IN-clause limits
    wo_ids = [str(wo['wo_id']) for wo in erp_wos]
    local_wos_list = []
    for i in range(0, len(wo_ids), CHUNK_SIZE):
        chunk = wo_ids[i:i + CHUNK_SIZE]
        local_wos_list.extend(WorkOrderAssignment.query.filter(WorkOrderAssignment.wo_id.in_(chunk)).all())
    local_wos = {a.wo_id: a for a in local_wos_list}

    # Staff for dropdown
    staff = Pickster.query.order_by(Pickster.name).all()

    # Merge and Group data
    grouped_wos = {}
    for erp_wo in erp_wos:
        wo_id_str = str(erp_wo['wo_id'])
        local_wo = local_wos.get(wo_id_str)

        erp_wo['assigned_to'] = local_wo.assigned_to.name if local_wo and local_wo.assigned_to else None
        erp_wo['local_status'] = local_wo.status if local_wo else erp_wo.get('status', 'Open')

        so_num = str(erp_wo['so_number'])
        if so_num not in grouped_wos:
            grouped_wos[so_num] = {
                'so_number': so_num,
                'customer_name': erp_wo.get('customer_name', 'Unknown'),
                'reference': erp_wo.get('reference', ''),
                'wo_rows': [],
                'count': 0
            }

        grouped_wos[so_num]['wo_rows'].append(erp_wo)
        grouped_wos[so_num]['count'] += 1

    # Convert to list and sort (descending SO tends to be newest)
    sorted_groups = sorted(grouped_wos.values(), key=lambda x: x['so_number'], reverse=True)

    return render_template('supervisor/wo_board.html', grouped_wos=sorted_groups, staff=staff)


@main_bp.route('/supervisor/assign_wo', methods=['POST'])
def assign_wo():
    # Support both bulk and single assignment
    staff_id = request.form.get('staff_id')

    # We expect a list of JSON-encoded WO objects if coming from bulk assign
    selected_data = request.form.getlist('selected_wos[]')

    if not selected_data:
        # Fallback for single legacy assignment if needed
        wo_id = request.form.get('wo_id')
        if wo_id:
            # Construct a single list item
            selected_data = [json.dumps({
                'wo_id': wo_id,
                'so_number': request.form.get('so_number'),
                'item_number': request.form.get('item_number'),
                'description': request.form.get('description')
            })]
        else:
            flash("No work orders selected.", "danger")
            return redirect(url_for('main.supervisor_work_orders'))

    count = 0
    for item_json in selected_data:
        try:
            item = json.loads(item_json)
            wo_id = str(item.get('wo_id'))
            so_number = str(item.get('so_number'))
            item_number = item.get('item_number')
            description = item.get('description')

            # Check if local assignment record exists
            local_wo = WorkOrderAssignment.query.filter_by(wo_id=wo_id).first()

            if not staff_id:
                # Clear assignment
                if local_wo:
                    local_wo.assigned_to_id = None
                    local_wo.status = 'Open'
            else:
                if not local_wo:
                    # Create local assignment record
                    local_wo = WorkOrderAssignment(
                        wo_id=wo_id,
                        sales_order_number=so_number,
                        item_number=item_number,
                        description=description,
                        assigned_to_id=staff_id,
                        status='Assigned'
                    )
                    db.session.add(local_wo)
                else:
                    # Update existing record
                    local_wo.assigned_to_id = staff_id
                    local_wo.status = 'Assigned'
            count += 1
        except Exception as e:
            print(f"Error assigning WO: {e}")
            continue

    db.session.commit()
    flash(f"{count} Work Order(s) updated successfully.", "success")
    return redirect(url_for('main.supervisor_work_orders'))

from flask import render_template, request, redirect, url_for, jsonify
from datetime import datetime

from app.extensions import db
from app.Models.models import Pickster, PickAssignment
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import _get_branch


@main_bp.route('/warehouse')
def warehouse_select():
    return render_template('warehouse/select_handling.html')


@main_bp.route('/warehouse/list')
def warehouse_list():
    code = request.args.get('code')
    erp = ERPService()
    raw_picks = erp.get_open_picks()

    # Filter by selected Handling Code and Group by SO
    grouped_picks = {}
    for pick in raw_picks:
        # Check if pick matches the selected code (case insensitive check just in case)
        if pick['handling_code'] and pick['handling_code'].lower() == code.lower():
            so = pick['so_number']

            if so not in grouped_picks:
                grouped_picks[so] = []

            grouped_picks[so].append(pick)

    return render_template('warehouse/view_picks.html', grouped_picks=grouped_picks, handling_code=code)


@main_bp.route('/warehouse/board')
def warehouse_board():
    erp = ERPService()
    summary = erp.get_open_so_summary(branch=_get_branch())

    assignments = PickAssignment.query.all()
    assignment_map = {a.so_number: a.picker_id for a in assignments}

    pickers = Pickster.query.filter_by(user_type='picker').order_by(Pickster.name).all()
    picker_map = {p.id: p for p in pickers}

    final_summary = []
    for item in summary:
        so_num = item['so_number']
        picker_id = assignment_map.get(so_num)
        item['assigned_picker'] = picker_map.get(picker_id) if picker_id else None
        final_summary.append(item)

    return render_template('warehouse/picks_board.html', summary=final_summary, pickers=pickers)


@main_bp.route('/warehouse/board/orders')
def board_orders():
    """
    Main Order Board: Aggregates multiple handling codes into a single SO card.
    """
    erp = ERPService()
    order_summary = erp.get_open_order_board_summary(branch=_get_branch())

    # Fetch assignments (SO level)
    so_numbers = [item['so_number'] for item in order_summary]
    assignments = {
        a.so_number: a.picker_id
        for a in PickAssignment.query.filter(PickAssignment.so_number.in_(so_numbers)).all()
    } if so_numbers else {}
    picker_ids = [pid for pid in assignments.values() if pid]
    pickers = {
        p.id: p
        for p in Pickster.query.filter(
            Pickster.user_type == 'picker',
            Pickster.id.in_(picker_ids),
        ).all()
    } if picker_ids else {}

    for item in order_summary:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = pickers.get(picker_id) if picker_id else None

    return render_template('warehouse/order_board.html', orders=order_summary)


@main_bp.route('/warehouse/board/tv/<handling_code>')
def board_tv(handling_code):
    """
    Department-Specific TV Board: Shows only one handling code.
    Designed for large displays.
    """
    erp = ERPService()
    raw_summary = erp.get_open_so_summary(branch=_get_branch())

    # Filter for specific handling code
    filtered_summary = [item for item in raw_summary if item['handling_code'] and item['handling_code'].upper() == handling_code.upper()]

    # Fetch assignments
    assignments = {a.so_number: a.picker_id for a in PickAssignment.query.all()}
    pickers = {p.id: p for p in Pickster.query.filter_by(user_type='picker').all()}

    for item in filtered_summary:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = pickers.get(picker_id) if picker_id else None

    return render_template('warehouse/tv_board.html', summary=filtered_summary, handling_code=handling_code.upper())


@main_bp.route('/warehouse/assign', methods=['POST'])
def assign_picker():
    so_number = request.form.get('so_number')
    picker_id = request.form.get('picker_id')

    # Check if assignment exists
    assignment = PickAssignment.query.filter_by(so_number=so_number).first()

    if not picker_id:
        # If picker_id is empty, remove assignment
        if assignment:
            db.session.delete(assignment)
    else:
        if assignment:
            assignment.picker_id = picker_id
            assignment.assigned_at = datetime.utcnow()
        else:
            new_assignment = PickAssignment(so_number=so_number, picker_id=picker_id)
            db.session.add(new_assignment)

    db.session.commit()
    return redirect(url_for('main.warehouse_board'))


@main_bp.route('/warehouse/detail/<so_number>')
@main_bp.route('/warehouse/order/<so_number>')
def pick_detail(so_number):
    erp = ERPService()
    header = erp.get_so_header(so_number)
    items = erp.get_so_details(so_number)
    return render_template('warehouse/pick_detail.html', so_number=so_number, header=header, items=items)


@main_bp.route('/warehouse/wh-detail/<so_number>')
def warehouse_detail(so_number):
    """Alias kept for backwards-compatible links in sales templates."""
    return redirect(url_for('main.pick_detail', so_number=so_number))

from flask import render_template

from app.Models.models import Pickster, PickAssignment
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import _tv_context


@main_bp.route('/tv/<branch>/picks')
def tv_open_picks(branch):
    """Open picks TV display for a specific branch."""
    ctx = _tv_context(branch)
    normalized = ctx['tv_branch']
    erp = ERPService()
    summary = erp.get_open_so_summary(branch=normalized)

    assignments = PickAssignment.query.filter(
        (PickAssignment.branch_code == normalized) | (PickAssignment.branch_code == None)
    ).all()
    assignment_map = {a.so_number: a.picker_id for a in assignments}
    pickers = Pickster.query.filter_by(user_type='picker').order_by(Pickster.name).all()
    picker_map = {p.id: p for p in pickers}

    for item in summary:
        picker_id = assignment_map.get(item['so_number'])
        item['assigned_picker'] = picker_map.get(picker_id) if picker_id else None

    return render_template('tv/open_picks.html', summary=summary, **ctx)


@main_bp.route('/tv/<branch>/board/<handling_code>')
def tv_board_branch(branch, handling_code):
    """Department TV board for a specific branch + handling code."""
    ctx = _tv_context(branch)
    normalized = ctx['tv_branch']
    erp = ERPService()
    raw_summary = erp.get_open_so_summary(branch=normalized)

    filtered = [item for item in raw_summary
                if item.get('handling_code') and item['handling_code'].upper() == handling_code.upper()]

    assignments = {a.so_number: a.picker_id for a in PickAssignment.query.filter(
        (PickAssignment.branch_code == normalized) | (PickAssignment.branch_code == None)
    ).all()}
    pickers = {p.id: p for p in Pickster.query.filter_by(user_type='picker').all()}

    for item in filtered:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = pickers.get(picker_id) if picker_id else None

    return render_template('tv/tv_board.html', summary=filtered,
                           handling_code=handling_code.upper(), **ctx)

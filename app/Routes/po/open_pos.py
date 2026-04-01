"""PO open-PO routes — list and detail views for open purchase orders."""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

from app.auth import get_current_user, role_required
from app.Models.models import POSubmission
from app.Routes.po import po_bp
from app.Routes.po.helpers import _current_branch, _user_roles


@po_bp.route("/open-pos")
@role_required("supervisor", "admin")
def open_pos():
    from app.Services.po_service import get_submission_summary_for_pos, list_open_pos_for_branch
    current_user = get_current_user()
    user_roles = _user_roles()
    user_branch = _current_branch()
    branch_param = request.args.get("branch", "")

    if "admin" in user_roles:
        branch = branch_param or None
    else:
        branch = user_branch or None

    try:
        pos = list_open_pos_for_branch(branch)
    except Exception as e:
        current_app.logger.error(f"open_pos query error: {e}")
        pos = []
        flash(
            "Could not load open POs. Verify that app_po_* read-model views are deployed.",
            "warning",
        )

    po_numbers = [p.get("po_number") for p in pos if p.get("po_number")]
    submission_counts = get_submission_summary_for_pos(po_numbers)

    return render_template(
        "po/open_pos.html",
        pos=pos,
        submission_counts=submission_counts,
        branch_filter=branch,
        branch_param=branch_param,
        user_roles=user_roles,
    )


@po_bp.route("/open-pos/<po_number>")
@role_required("supervisor", "admin")
def open_po_detail(po_number):
    from app.Services.po_service import get_purchase_order
    po_number = po_number.strip().upper()

    try:
        po = get_purchase_order(po_number)
    except Exception as e:
        current_app.logger.error(f"open_po_detail query error for {po_number}: {e}")
        po = None

    if po is None:
        flash(f"PO {po_number} not found.", "warning")
        return redirect(url_for("po.open_pos"))

    submissions = (
        POSubmission.query
        .filter(POSubmission.po_number == po_number)
        .order_by(POSubmission.created_at.desc())
        .all()
    )

    return render_template(
        "po/open_po_detail.html",
        po=po,
        po_number=po_number,
        submissions=submissions,
    )

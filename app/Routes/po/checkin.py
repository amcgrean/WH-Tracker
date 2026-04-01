"""PO worker routes — check-in wizard and submission history."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import render_template, request

from app.auth import get_current_user, role_required
from app.Models.models import POSubmission
from app.Routes.po import po_bp


@po_bp.route("/")
@role_required("purchasing", "warehouse", "ops", "supervisor", "admin")
def checkin():
    return render_template("po/checkin.html")


@po_bp.route("/history")
@role_required("purchasing", "warehouse", "ops", "supervisor", "admin")
def history():
    current_user = get_current_user()
    user_id = current_user["id"]
    status_filter = request.args.get("status", "all")
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 50

    since = datetime.utcnow() - timedelta(days=30)
    query = POSubmission.query.filter(
        POSubmission.submitted_by == user_id,
        POSubmission.created_at >= since,
    )
    if status_filter != "all":
        query = query.filter(POSubmission.status == status_filter)

    query = query.order_by(POSubmission.created_at.desc())
    total = query.count()
    submissions = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        "po/history.html",
        submissions=submissions,
        status_filter=status_filter,
        page=page,
        total=total,
        per_page=per_page,
        total_pages=max(1, (total + per_page - 1) // per_page),
    )

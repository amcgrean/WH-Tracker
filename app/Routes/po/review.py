"""PO review routes — submission review dashboard and detail."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import flash, redirect, render_template, request, session, url_for

from app.auth import SESSION_USER_ID, get_current_user, role_required
from app.extensions import db
from app.Models.models import POSubmission
from app.Routes.po import po_bp
from app.Routes.po.helpers import _current_branch, _submission_scope_branch, _user_roles
from app.Services.purchasing_service import PurchasingService


@po_bp.route("/review")
@role_required("ops", "supervisor", "admin")
def review_dashboard():
    current_user = get_current_user()
    user_roles = _user_roles()
    user_branch = _current_branch()

    status_filter = request.args.get("status", "all")
    branch_param = request.args.get("branch", "")
    days = max(1, int(request.args.get("days", 7) or 7))
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 50

    since = datetime.utcnow() - timedelta(days=days)
    query = POSubmission.query.filter(POSubmission.created_at >= since)

    # Branch scoping: ops users are locked to their branch; supervisor/admin can filter freely
    scope_branch = _submission_scope_branch(user_roles, user_branch)
    if scope_branch:
        query = query.filter(POSubmission.branch == scope_branch)
    elif branch_param:
        query = query.filter(POSubmission.branch == branch_param)

    if status_filter != "all":
        query = query.filter(POSubmission.status == status_filter)

    query = query.order_by(POSubmission.created_at.desc())
    total = query.count()
    submissions = query.offset((page - 1) * per_page).limit(per_page).all()

    # Branch choices for filter dropdown (supervisor/admin only)
    available_branches = []
    if scope_branch is None:
        from sqlalchemy import distinct
        available_branches = [
            r[0] for r in
            db.session.query(distinct(POSubmission.branch))
            .filter(POSubmission.branch.isnot(None))
            .order_by(POSubmission.branch)
            .all()
        ]

    return render_template(
        "po/review_dashboard.html",
        submissions=submissions,
        status_filter=status_filter,
        branch_param=branch_param,
        scope_branch=scope_branch,
        available_branches=available_branches,
        days=days,
        page=page,
        total=total,
        per_page=per_page,
        total_pages=max(1, (total + per_page - 1) // per_page),
        user_roles=user_roles,
        last_updated=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "Z",
    )


@po_bp.route("/review/<submission_id>", methods=["GET", "POST"])
@role_required("ops", "supervisor", "admin")
def review_detail(submission_id):
    sub = POSubmission.query.get_or_404(submission_id)

    if request.method == "POST":
        new_status = (request.form.get("status") or "").strip()
        reviewer_notes = (request.form.get("reviewer_notes") or "").strip()

        if new_status not in ("pending", "reviewed", "flagged"):
            flash("Invalid status value.", "danger")
            return redirect(url_for("po.review_detail", submission_id=submission_id))

        sub.status = new_status
        sub.reviewer_notes = reviewer_notes or None
        sub.reviewed_by = session.get(SESSION_USER_ID)
        sub.reviewed_at = datetime.now(timezone.utc)
        PurchasingService().sync_submission_queue_status(sub, reviewer_user_id=sub.reviewed_by)
        db.session.commit()
        flash("Review saved.", "success")
        return redirect(url_for("po.review_dashboard"))

    return render_template("po/review_detail.html", submission=sub)

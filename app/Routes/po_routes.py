"""
po_routes.py
------------
Blueprint: po  (prefix /po)

Worker routes:
    GET  /po/              — 3-step PO check-in wizard
    GET  /po/history       — worker's own submission history

Review routes (ops/supervisor/admin):
    GET       /po/review              — submissions dashboard
    GET/POST  /po/review/<id>         — submission detail + review action

Open PO routes (supervisor/admin):
    GET  /po/open-pos                 — open PO list
    GET  /po/open-pos/<po_number>     — full PO detail

API (JSON):
    GET   /po/api/search              — PO search (q, limit)
    GET   /po/api/po/<po_number>      — full PO detail JSON
    POST  /po/api/upload              — upload photo to R2
    POST  /po/api/submissions         — create submission
    GET   /po/api/submissions         — list submissions (polling)
    GET   /po/api/submissions/<id>    — single submission JSON
    PATCH /po/api/submissions/<id>    — update status/notes
"""
from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.auth import (
    SESSION_USER_BRANCH,
    SESSION_USER_ID,
    SESSION_USER_ROLES,
    get_current_user,
    login_required,
    role_required,
)
from app.extensions import db
from app.Models.models import AppUser, POSubmission

po_bp = Blueprint("po", __name__, url_prefix="/po")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _current_branch() -> str:
    return session.get(SESSION_USER_BRANCH) or ""


def _user_roles() -> set:
    return set(session.get(SESSION_USER_ROLES, []))


def _submission_scope_branch(user_roles: set, user_branch: str) -> str | None:
    """Return the branch to scope submissions queries to, or None for all branches."""
    if "admin" in user_roles or "supervisor" in user_roles:
        return None
    return user_branch or None


def _sanitize_po(po_number: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", po_number)


def _get_r2_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("R2_ENDPOINT_URL", ""),
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        region_name="auto",
    )


def _sub_to_dict(sub: POSubmission) -> dict:
    return {
        "id": sub.id,
        "po_number": sub.po_number,
        "image_urls": sub.image_urls or [],
        "thumbnail": (sub.image_urls or [None])[0],
        "supplier_name": sub.supplier_name,
        "po_status": sub.po_status,
        "notes": sub.notes,
        "status": sub.status,
        "submitted_by": sub.submitted_by,
        "submitted_username": sub.submitted_username,
        "branch": sub.branch,
        "reviewer_notes": sub.reviewer_notes,
        "reviewed_by": sub.reviewed_by,
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


# ---------------------------------------------------------------------------
# Worker routes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Review routes
# ---------------------------------------------------------------------------

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
        db.session.commit()
        flash("Review saved.", "success")
        return redirect(url_for("po.review_dashboard"))

    return render_template("po/review_detail.html", submission=sub)


# ---------------------------------------------------------------------------
# Open PO routes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# API — PO lookup
# ---------------------------------------------------------------------------

@po_bp.route("/api/search")
@login_required
def api_search_pos():
    from app.Services.po_service import search_purchase_orders
    q = (request.args.get("q") or "").strip()
    limit = min(max(1, int(request.args.get("limit", 25) or 25)), 25)

    if len(q) < 2:
        return jsonify([])

    try:
        results = search_purchase_orders(q, limit=limit)
    except Exception as e:
        current_app.logger.error(f"PO search error: {e}")
        return jsonify({"error": "Search unavailable"}), 503

    return jsonify(results)


@po_bp.route("/api/po/<po_number>")
@login_required
def api_get_po(po_number):
    from app.Services.po_service import get_purchase_order
    po_number = po_number.strip().upper()

    try:
        po = get_purchase_order(po_number)
    except Exception as e:
        current_app.logger.error(f"api_get_po error for {po_number}: {e}")
        return jsonify({"error": "ERP unavailable"}), 503

    if po is None:
        return jsonify({"error": "Not found"}), 404

    return jsonify(po)


# ---------------------------------------------------------------------------
# API — photo upload
# ---------------------------------------------------------------------------

@po_bp.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    content_type = f.content_type or f.mimetype or ""
    if not content_type.startswith("image/"):
        return jsonify({"error": "File must be an image"}), 400

    po_number = (request.form.get("po_number") or "unknown").strip()
    sanitized_po = _sanitize_po(po_number)
    now = datetime.utcnow()
    key = (
        f"submissions/{now.year}/{now.month:02d}/"
        f"{sanitized_po}/{int(time.time())}-{uuid.uuid4().hex[:8]}.jpg"
    )

    bucket = os.environ.get("R2_BUCKET_NAME", "po-checkin-photos")
    public_url = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

    try:
        client = _get_r2_client()
        client.upload_fileobj(
            f.stream,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as e:
        current_app.logger.error(f"R2 upload error: {e}")
        return jsonify({"error": "Upload failed"}), 500

    return jsonify({"url": f"{public_url}/{key}", "key": key})


# ---------------------------------------------------------------------------
# API — submissions CRUD
# ---------------------------------------------------------------------------

@po_bp.route("/api/submissions", methods=["POST"])
@login_required
def api_create_submission():
    data = request.get_json(silent=True) or {}
    po_number = (data.get("po_number") or "").strip()
    image_urls = data.get("image_urls") or []
    notes = (data.get("notes") or "").strip() or None

    if not po_number:
        return jsonify({"error": "po_number is required"}), 400
    if not isinstance(image_urls, list):
        return jsonify({"error": "image_urls must be a list"}), 400

    current_user = get_current_user()
    user_branch = _current_branch()

    sub = POSubmission(
        id=str(uuid.uuid4()),
        po_number=po_number.upper(),
        image_urls=image_urls,
        supplier_name=(data.get("supplier_name") or "").strip() or None,
        po_status=(data.get("po_status") or "").strip() or None,
        notes=notes,
        status="pending",
        submitted_by=current_user["id"],
        submitted_username=current_user.get("display_name") or current_user.get("email", ""),
        branch=user_branch or None,
    )
    db.session.add(sub)
    db.session.commit()

    return jsonify({"id": sub.id, "status": sub.status}), 201


@po_bp.route("/api/submissions", methods=["GET"])
@login_required
def api_list_submissions():
    branch_param = request.args.get("branch", "")
    status_param = request.args.get("status", "")
    since_str = request.args.get("since", "")

    query = POSubmission.query

    # Role-based scope applied first
    user_roles = _user_roles()
    user_branch = _current_branch()
    scope = _submission_scope_branch(user_roles, user_branch)
    if scope:
        query = query.filter(POSubmission.branch == scope)

    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
            # Compare against naive UTC since our stored datetimes may be naive
            since_naive = since.replace(tzinfo=None)
            query = query.filter(POSubmission.created_at > since_naive)
        except (ValueError, TypeError):
            pass

    if branch_param and not scope:
        query = query.filter(POSubmission.branch == branch_param)
    if status_param:
        query = query.filter(POSubmission.status == status_param)

    submissions = query.order_by(POSubmission.created_at.desc()).limit(200).all()
    return jsonify([_sub_to_dict(s) for s in submissions])


@po_bp.route("/api/submissions/<submission_id>", methods=["GET"])
@login_required
def api_get_submission(submission_id):
    sub = POSubmission.query.get_or_404(submission_id)
    return jsonify(_sub_to_dict(sub))


@po_bp.route("/api/submissions/<submission_id>", methods=["PATCH"])
@role_required("ops", "supervisor", "admin")
def api_update_submission(submission_id):
    sub = POSubmission.query.get_or_404(submission_id)
    data = request.get_json(silent=True) or {}

    new_status = (data.get("status") or "").strip()
    if new_status and new_status not in ("pending", "reviewed", "flagged"):
        return jsonify({"error": "Invalid status"}), 400

    if new_status:
        sub.status = new_status
    if "reviewer_notes" in data:
        sub.reviewer_notes = (data["reviewer_notes"] or "").strip() or None
    sub.reviewed_by = session.get(SESSION_USER_ID)
    sub.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify(_sub_to_dict(sub))

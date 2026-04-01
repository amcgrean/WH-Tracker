"""PO API routes — search, upload, submissions CRUD, admin cache refresh."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from flask import current_app, jsonify, request, session

from app.auth import SESSION_USER_ID, get_current_user, login_required, role_required
from app.extensions import db
from app.Models.models import POSubmission
from app.Routes.po import po_bp
from app.Routes.po.helpers import (
    _current_branch,
    _sanitize_po,
    _sub_to_dict,
    _submission_scope_branch,
    _user_roles,
)
from app.Services.purchasing_service import PurchasingService


def _get_r2_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("R2_ENDPOINT_URL", ""),
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        region_name="auto",
    )


# ---------------------------------------------------------------------------
# PO lookup
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
# Photo upload
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
# Submissions CRUD
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
        supplier_key=(data.get("supplier_key") or "").strip() or None,
        po_status=(data.get("po_status") or "").strip() or None,
        submission_type=(data.get("submission_type") or "receiving_checkin").strip() or "receiving_checkin",
        priority=(data.get("priority") or "").strip().lower() or None,
        notes=notes,
        status="pending",
        submitted_by=current_user["id"],
        submitted_username=current_user.get("display_name") or current_user.get("email", ""),
        branch=user_branch or None,
    )
    db.session.add(sub)
    PurchasingService().ensure_submission_queue_item(sub, created_by_user_id=current_user["id"])
    db.session.commit()

    return jsonify({"id": sub.id, "status": sub.status, "queue_item_id": sub.queue_item_id}), 201


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
    if "priority" in data:
        sub.priority = (data.get("priority") or "").strip().lower() or sub.priority
    if "reviewer_notes" in data:
        sub.reviewer_notes = (data["reviewer_notes"] or "").strip() or None
    sub.reviewed_by = session.get(SESSION_USER_ID)
    sub.reviewed_at = datetime.now(timezone.utc)
    PurchasingService().sync_submission_queue_status(sub, reviewer_user_id=sub.reviewed_by)
    db.session.commit()

    return jsonify(_sub_to_dict(sub))


@po_bp.route("/api/admin/refresh-cache", methods=["POST"])
@role_required("admin")
def api_refresh_po_cache():
    """Force-refresh the app_po_header materialized view (admin only).

    The view is also refreshed automatically every 15 minutes by pg_cron.
    Use this when you need fresh data immediately after an ERP sync.
    """
    from sqlalchemy import text
    try:
        db.session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY public.app_po_header"))
        db.session.commit()
        return jsonify({"ok": True, "message": "PO cache refreshed."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

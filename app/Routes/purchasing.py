from __future__ import annotations

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from app.Services.purchasing_service import PurchasingService
from app.auth import get_current_user, permission_required, role_required


purchasing_bp = Blueprint("purchasing", __name__, url_prefix="/purchasing")


def _service() -> PurchasingService:
    return PurchasingService()


@purchasing_bp.route("/")
@role_required("purchasing", "manager", "ops", "supervisor", "admin")
def home():
    current_user = get_current_user() or {}
    if "purchasing" in (current_user.get("roles") or []) and "purchasing.all_branches.view" not in PurchasingService().permissions:
        return redirect(url_for("purchasing.buyer_dashboard"))
    return redirect(url_for("purchasing.manager_dashboard"))


@purchasing_bp.route("/manager")
@role_required("manager", "ops", "supervisor", "admin")
def manager_dashboard():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    payload = _service().get_manager_dashboard(current_user, system_id=system_id)
    return render_template("purchasing/manager_dashboard.html", dashboard=payload)


@purchasing_bp.route("/workspace")
@permission_required("purchasing.dashboard.view", "purchasing.branch.view")
def buyer_dashboard():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    payload = _service().get_buyer_workspace(current_user, system_id=system_id)
    return render_template("purchasing/buyer_dashboard.html", workspace=payload)


@purchasing_bp.route("/po/<po_number>")
@permission_required("purchasing.dashboard.view", "purchasing.po.review")
def po_workspace(po_number: str):
    payload = _service().get_po_workspace(po_number)
    if not payload["po"].get("header") and not payload["submissions"] and not payload["queue_items"]:
        abort(404)
    return render_template("purchasing/po_workspace.html", workspace=payload)


@purchasing_bp.route("/suggested-buys")
@permission_required("purchasing.dashboard.view", "purchasing.branch.view")
def suggested_buys():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    suggestions = _service()._suggested_buys(system_id=system_id or current_user.get("branch") or None)
    return render_template(
        "purchasing/suggested_buys.html",
        suggestions=suggestions,
        branch=system_id or current_user.get("branch") or "ALL",
        is_limited_preview=bool(suggestions),
    )


@purchasing_bp.route("/api/dashboard/manager")
@role_required("manager", "ops", "supervisor", "admin")
def api_manager_dashboard():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    return jsonify(_service().get_manager_dashboard(current_user, system_id=system_id))


@purchasing_bp.route("/api/dashboard/buyer")
@permission_required("purchasing.dashboard.view", "purchasing.branch.view")
def api_buyer_dashboard():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    return jsonify(_service().get_buyer_workspace(current_user, system_id=system_id))


@purchasing_bp.route("/api/queue")
@permission_required("purchasing.dashboard.view", "purchasing.branch.view")
def api_queue():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    return jsonify({"items": _service().list_work_queue(current_user, system_id=system_id, include_virtual=True)})


@purchasing_bp.route("/api/po/<po_number>")
@permission_required("purchasing.dashboard.view", "purchasing.po.review")
def api_po_workspace(po_number: str):
    return jsonify(_service().serialize_po_workspace(_service().get_po_workspace(po_number)))


@purchasing_bp.route("/api/suggested-buys")
@permission_required("purchasing.dashboard.view", "purchasing.branch.view")
def api_suggested_buys():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    suggestions = _service()._suggested_buys(system_id=system_id or current_user.get("branch") or None)
    return jsonify({"items": suggestions})


@purchasing_bp.route("/api/exceptions")
@permission_required("purchasing.dashboard.view", "purchasing.receiving.resolve")
def api_exceptions():
    current_user = get_current_user() or {}
    system_id = request.args.get("branch", "").strip().upper() or None
    queue = _service().list_work_queue(current_user, system_id=system_id, include_virtual=True)
    items = [item for item in queue if item["queue_type"] in {"receiving_checkin", "receiving_discrepancy", "overdue_po"}]
    return jsonify({"items": items})


@purchasing_bp.route("/api/po/<po_number>/notes", methods=["POST"])
@permission_required("purchasing.po.review")
def api_create_note(po_number: str):
    current_user = get_current_user() or {}
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "body is required"}), 400
    note = _service().create_note(current_user, po_number.strip().upper(), body)
    return jsonify({
        "id": note.id,
        "po_number": note.po_number,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
        "created_by": note.created_by.display_name if note.created_by else None,
    }), 201


@purchasing_bp.route("/api/tasks", methods=["POST"])
@permission_required("purchasing.queue.assign", "purchasing.po.review")
def api_create_task():
    current_user = get_current_user() or {}
    data = request.get_json(silent=True) or {}
    if not (data.get("title") or "").strip():
        return jsonify({"error": "title is required"}), 400
    task = _service().create_task(current_user, data)
    return jsonify({
        "id": task.id,
        "title": task.title,
        "po_number": task.po_number,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at.isoformat() if task.due_at else None,
    }), 201


@purchasing_bp.route("/api/approvals/<int:approval_id>", methods=["PATCH"])
@permission_required("purchasing.po.approve")
def api_update_approval(approval_id: int):
    current_user = get_current_user() or {}
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().lower()
    if status not in {"approved", "rejected", "pending"}:
        return jsonify({"error": "invalid status"}), 400
    approval = _service().update_approval(current_user, approval_id, status, data.get("decision_notes"))
    if not approval:
        return jsonify({"error": "Approval not found"}), 404
    return jsonify({
        "id": approval.id,
        "status": approval.status,
        "decision_notes": approval.decision_notes,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
    })

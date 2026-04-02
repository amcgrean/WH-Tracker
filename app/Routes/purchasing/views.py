"""Purchasing page routes — dashboards, workspaces, suggested buys."""
from __future__ import annotations

from flask import redirect, render_template, request, url_for

from app.auth import get_current_user, permission_required, role_required
from app.Routes.purchasing import purchasing_bp
from app.Services.purchasing_service import PurchasingService


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
        from flask import abort
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

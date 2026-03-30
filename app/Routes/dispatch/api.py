from datetime import datetime
from flask import jsonify, request, send_file
from app.Routes.dispatch import dispatch_bp
from app.Routes.dispatch.helpers import dispatch_service, erp_service, samsara_service


@dispatch_bp.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "time_utc": datetime.utcnow().isoformat() + "Z",
            "using_cloud_mirror": True,
            "legacy_erp_fallback_enabled": erp_service.allow_legacy_erp_fallback,
        }
    )


@dispatch_bp.get("/api/branches")
def branches():
    return jsonify(dispatch_service.get_branch_choices())


@dispatch_bp.post("/api/manifest")
def manifest():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list) or not (1 <= len(items) <= 10):
        return jsonify({"error": "Provide between 1 and 10 items."}), 400
    pdf_buffer = dispatch_service.generate_manifest_pdf(items)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="dispatch-manifest.pdf",
    )


@dispatch_bp.get("/api/vehicles/live")
def live_vehicles():
    branch = request.args.get("branch")
    limit = request.args.get("limit", type=int)
    payload = samsara_service.get_dispatch_vehicle_payload(branch=branch, limit=limit)
    return jsonify(payload)

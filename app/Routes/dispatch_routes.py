from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, send_file

from app.Services.dispatch_service import DispatchService
from app.Services.erp_service import ERPService
from app.Services.samsara_service import SamsaraService

dispatch = Blueprint("dispatch", __name__, url_prefix="/dispatch")
dispatch_service = DispatchService()
erp_service = ERPService()
samsara_service = SamsaraService()


def _add_business_days(start_date: date, days: int) -> date:
    result = start_date
    sign = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining > 0:
        result += timedelta(days=sign)
        if result.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return result


def _parse_iso_date(value: str, fallback: date) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return fallback


@dispatch.get("/")
def index():
    return render_template("dispatch/index.html")


@dispatch.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "time_utc": datetime.utcnow().isoformat() + "Z",
            "using_db": dispatch_service.using_db(),
        }
    )


@dispatch.get("/api/branches")
def branches():
    return jsonify(dispatch_service.get_branch_choices())


@dispatch.get("/api/stops")
def stops():
    today = date.today()
    default_start = _add_business_days(today, -7)
    default_end = _add_business_days(today, 1)
    start = _parse_iso_date(request.args.get("start", default_start.isoformat()), default_start)
    end = _parse_iso_date(request.args.get("end", default_end.isoformat()), default_end)
    statuses = request.args.get("status")
    branch = request.args.get("branch")
    sale_types = request.args.get("sale_types")
    route_id = request.args.get("route_id")
    driver = request.args.get("driver")
    debug_mode = request.args.get("debug", "").lower() in ("1", "true", "yes", "y")

    try:
        rows = erp_service.get_dispatch_stops(
            start=start,
            end=end,
            sale_types=sale_types,
            status_filter=statuses,
            route_id=route_id,
            driver=driver,
            include_no_gps=True,
            branches=branch,
        )
    except Exception:
        rows = dispatch_service.get_stops(
            start=start,
            end=end,
            sale_types=sale_types,
            status_filter=statuses,
            route_id=route_id,
            driver=driver,
            include_no_gps=True,
            branches=branch,
        )
    return jsonify(rows)


@dispatch.get("/api/orders/<int:so_id>/lines")
def shipment_lines(so_id: int):
    shipment_num = request.args.get("shipment_num")
    shipment_value = int(shipment_num) if shipment_num not in (None, "", "null") else None
    try:
        lines = erp_service.get_dispatch_shipment_lines(so_id, shipment_value, limit=200)
    except Exception:
        lines = dispatch_service.get_shipment_lines(so_id, shipment_value, limit=200)
    return jsonify(lines)


@dispatch.post("/api/manifest")
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


@dispatch.get("/api/vehicles/live")
def live_vehicles():
    branch = request.args.get("branch")
    limit = request.args.get("limit", type=int)
    payload = samsara_service.get_dispatch_vehicle_payload(branch=branch, limit=limit)
    return jsonify(payload)

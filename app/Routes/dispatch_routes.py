from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, send_file, session

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
            "using_cloud_mirror": True,
            "legacy_erp_fallback_enabled": erp_service.allow_legacy_erp_fallback,
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
    return jsonify(rows)


@dispatch.get("/api/orders/<int:so_id>/lines")
def shipment_lines(so_id: int):
    shipment_num = request.args.get("shipment_num")
    shipment_value = int(shipment_num) if shipment_num not in (None, "", "null") else None
    lines = erp_service.get_dispatch_shipment_lines(so_id, shipment_value, limit=200)
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


def _current_user_id():
    return session.get("user_id")


def _parse_stops_params():
    """Parse common date/branch/filter params used by stops endpoints."""
    today = date.today()
    default_start = _add_business_days(today, -7)
    default_end = _add_business_days(today, 1)
    return {
        "start": _parse_iso_date(request.args.get("start", default_start.isoformat()), default_start),
        "end": _parse_iso_date(request.args.get("end", default_end.isoformat()), default_end),
        "status_filter": request.args.get("status"),
        "branch": request.args.get("branch"),
        "sale_types": request.args.get("sale_types"),
        "route_id": request.args.get("route_id"),
        "driver": request.args.get("driver"),
    }


# ------------------------------------------------------------------
# Enriched Stops
# ------------------------------------------------------------------

@dispatch.get("/api/stops/enriched")
def enriched_stops():
    p = _parse_stops_params()
    rows = erp_service.get_enriched_dispatch_stops(
        start=p["start"],
        end=p["end"],
        sale_types=p["sale_types"],
        status_filter=p["status_filter"],
        route_id=p["route_id"],
        driver=p["driver"],
        include_no_gps=True,
        branches=p["branch"],
    )
    return jsonify(rows)


# ------------------------------------------------------------------
# KPIs
# ------------------------------------------------------------------

@dispatch.get("/api/kpis")
def kpis():
    today = date.today()
    kpi_date = _parse_iso_date(request.args.get("date", today.isoformat()), today)
    branch = request.args.get("branch")
    data = dispatch_service.get_daily_kpis(kpi_date, branch)
    return jsonify(data)


# ------------------------------------------------------------------
# Routes CRUD
# ------------------------------------------------------------------

@dispatch.get("/api/routes")
def list_routes():
    today = date.today()
    route_date = _parse_iso_date(request.args.get("date", today.isoformat()), today)
    branch = request.args.get("branch")
    routes = dispatch_service.get_routes_for_date(route_date, branch)
    return jsonify(routes)


@dispatch.post("/api/routes")
def create_route():
    payload = request.get_json(silent=True) or {}
    route_date = _parse_iso_date(payload.get("route_date", ""), date.today())
    route_name = payload.get("route_name", "").strip()
    branch_code = payload.get("branch_code", "").strip()
    if not route_name or not branch_code:
        return jsonify({"error": "route_name and branch_code are required."}), 400
    route = dispatch_service.create_route(
        route_date=route_date,
        route_name=route_name,
        branch_code=branch_code,
        driver_name=payload.get("driver_name"),
        truck_id=payload.get("truck_id"),
        notes=payload.get("notes"),
        user_id=_current_user_id(),
    )
    return jsonify(route), 201


@dispatch.put("/api/routes/<int:route_id>")
def update_route(route_id):
    payload = request.get_json(silent=True) or {}
    route = dispatch_service.update_route(route_id, **payload)
    if route is None:
        return jsonify({"error": "Route not found."}), 404
    return jsonify(route)


@dispatch.delete("/api/routes/<int:route_id>")
def delete_route(route_id):
    ok = dispatch_service.delete_route(route_id)
    if not ok:
        return jsonify({"error": "Route not found."}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Route Stops
# ------------------------------------------------------------------

@dispatch.post("/api/routes/<int:route_id>/stops")
def add_route_stops(route_id):
    payload = request.get_json(silent=True) or {}
    stop_defs = payload.get("stops") or []
    if not stop_defs:
        return jsonify({"error": "Provide a 'stops' array."}), 400
    stops = dispatch_service.add_stops_to_route(route_id, stop_defs)
    if not stops:
        return jsonify({"error": "Route not found."}), 404
    return jsonify(stops), 201


@dispatch.put("/api/routes/<int:route_id>/stops/reorder")
def reorder_route_stops(route_id):
    payload = request.get_json(silent=True) or {}
    ordered_ids = payload.get("stop_ids") or []
    if not ordered_ids:
        return jsonify({"error": "Provide a 'stop_ids' array."}), 400
    dispatch_service.reorder_stops(route_id, ordered_ids)
    return jsonify({"ok": True})


@dispatch.delete("/api/routes/<int:route_id>/stops/<int:stop_id>")
def remove_route_stop(route_id, stop_id):
    ok = dispatch_service.remove_stop(route_id, stop_id)
    if not ok:
        return jsonify({"error": "Stop not found."}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Drivers
# ------------------------------------------------------------------

@dispatch.get("/api/drivers")
def list_drivers():
    branch = request.args.get("branch")
    drivers = dispatch_service.get_drivers(branch)
    return jsonify(drivers)


@dispatch.post("/api/drivers")
def create_driver():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required."}), 400
    driver = dispatch_service.create_driver(
        name=name,
        phone=payload.get("phone"),
        default_truck_id=payload.get("default_truck_id"),
        branch_code=payload.get("branch_code"),
        notes=payload.get("notes"),
    )
    return jsonify(driver), 201


@dispatch.put("/api/drivers/<int:driver_id>")
def update_driver(driver_id):
    payload = request.get_json(silent=True) or {}
    driver = dispatch_service.update_driver(driver_id, **payload)
    if driver is None:
        return jsonify({"error": "Driver not found."}), 404
    return jsonify(driver)


@dispatch.post("/api/drivers/seed-from-erp")
def seed_drivers():
    branch = request.args.get("branch")
    created = dispatch_service.seed_drivers_from_erp(branch)
    return jsonify({"created": len(created), "drivers": created})


# ------------------------------------------------------------------
# Truck Assignments
# ------------------------------------------------------------------

@dispatch.get("/api/trucks")
def list_trucks():
    today = date.today()
    assignment_date = _parse_iso_date(
        request.args.get("date", today.isoformat()), today
    )
    branch = request.args.get("branch")
    assignments = dispatch_service.get_truck_assignments(assignment_date, branch)

    # Also fetch live Samsara vehicles to merge
    vehicles = samsara_service.get_dispatch_vehicle_payload(branch=branch) or {}
    vehicle_list = vehicles.get("vehicles") or []

    # Build merged list: Samsara vehicles + their assignments
    assigned_ids = {a["samsara_vehicle_id"] for a in assignments}
    assign_map = {a["samsara_vehicle_id"]: a for a in assignments}

    merged = []
    for v in vehicle_list:
        vid = v.get("id") or v.get("name")
        assignment = assign_map.get(vid, {})
        merged.append({
            **v,
            "assignment": assignment if assignment else None,
        })

    # Include assignments for vehicles not in current Samsara response
    for a in assignments:
        if a["samsara_vehicle_id"] not in {v.get("id") or v.get("name") for v in vehicle_list}:
            merged.append({
                "id": a["samsara_vehicle_id"],
                "name": a["samsara_vehicle_name"],
                "branch": a["branch_code"],
                "assignment": a,
            })

    return jsonify({"trucks": merged, "assignments": assignments})


@dispatch.post("/api/trucks/assignments")
def upsert_truck_assignment():
    payload = request.get_json(silent=True) or {}
    assignment_date = _parse_iso_date(
        payload.get("assignment_date", date.today().isoformat()), date.today()
    )
    vehicle_id = payload.get("samsara_vehicle_id", "").strip()
    if not vehicle_id:
        return jsonify({"error": "samsara_vehicle_id is required."}), 400
    assignment = dispatch_service.upsert_truck_assignment(
        assignment_date=assignment_date,
        samsara_vehicle_id=vehicle_id,
        samsara_vehicle_name=payload.get("samsara_vehicle_name"),
        branch_code=payload.get("branch_code", ""),
        driver_id=payload.get("driver_id"),
        route_id=payload.get("route_id"),
        notes=payload.get("notes"),
        user_id=_current_user_id(),
    )
    return jsonify(assignment)


@dispatch.put("/api/trucks/assignments/<int:assignment_id>")
def update_truck_assignment(assignment_id):
    from app.Models.dispatch_models import DispatchTruckAssignment
    from app.extensions import db

    assignment = DispatchTruckAssignment.query.get(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    payload = request.get_json(silent=True) or {}
    for key in ("driver_id", "route_id", "notes"):
        if key in payload:
            setattr(assignment, key, payload[key])
    db.session.commit()
    return jsonify(assignment.to_dict())


@dispatch.post("/api/trucks/assignments/copy-previous")
def copy_previous_assignments():
    payload = request.get_json(silent=True) or {}
    target_date = _parse_iso_date(
        payload.get("target_date", date.today().isoformat()), date.today()
    )
    branch = payload.get("branch", "")
    if not branch:
        return jsonify({"error": "branch is required."}), 400
    created = dispatch_service.copy_previous_assignments(
        target_date, branch, _current_user_id()
    )
    return jsonify({"copied": len(created), "assignments": created})


# ------------------------------------------------------------------
# Order Detail Helpers (customer AR, work orders, timeline)
# ------------------------------------------------------------------

@dispatch.get("/api/customers/<cust_key>/summary")
def customer_summary(cust_key):
    ar = erp_service.get_customer_ar_summary(cust_key)
    return jsonify(ar)


@dispatch.get("/api/orders/<so_id>/timeline")
def order_timeline(so_id):
    events = erp_service.get_order_timeline(so_id)
    return jsonify(events)


@dispatch.get("/api/orders/<so_id>/work-orders")
def order_work_orders(so_id):
    wos = erp_service.get_order_work_orders(so_id)
    return jsonify(wos)

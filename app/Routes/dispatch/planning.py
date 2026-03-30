"""Route planning, driver roster, truck assignments, and KPI endpoints."""

from datetime import date
from flask import jsonify, request, session
from app.Routes.dispatch import dispatch_bp
from app.Routes.dispatch.helpers import (
    _parse_iso_date, dispatch_service, samsara_service,
)


def _current_user_id():
    return session.get("user_id")


# ------------------------------------------------------------------
# KPIs
# ------------------------------------------------------------------

@dispatch_bp.get("/api/kpis")
def kpis():
    today = date.today()
    kpi_date = _parse_iso_date(request.args.get("date", today.isoformat()), today)
    branch = request.args.get("branch")
    data = dispatch_service.get_daily_kpis(kpi_date, branch)
    return jsonify(data)


# ------------------------------------------------------------------
# Routes CRUD
# ------------------------------------------------------------------

@dispatch_bp.get("/api/routes")
def list_routes():
    today = date.today()
    route_date = _parse_iso_date(request.args.get("date", today.isoformat()), today)
    branch = request.args.get("branch")
    routes = dispatch_service.get_routes_for_date(route_date, branch)
    return jsonify(routes)


@dispatch_bp.post("/api/routes")
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


@dispatch_bp.put("/api/routes/<int:route_id>")
def update_route(route_id):
    payload = request.get_json(silent=True) or {}
    route = dispatch_service.update_route(route_id, **payload)
    if route is None:
        return jsonify({"error": "Route not found."}), 404
    return jsonify(route)


@dispatch_bp.delete("/api/routes/<int:route_id>")
def delete_route(route_id):
    ok = dispatch_service.delete_route(route_id)
    if not ok:
        return jsonify({"error": "Route not found."}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Route Stops
# ------------------------------------------------------------------

@dispatch_bp.post("/api/routes/<int:route_id>/stops")
def add_route_stops(route_id):
    payload = request.get_json(silent=True) or {}
    stop_defs = payload.get("stops") or []
    if not stop_defs:
        return jsonify({"error": "Provide a 'stops' array."}), 400
    stops = dispatch_service.add_stops_to_route(route_id, stop_defs)
    if not stops:
        return jsonify({"error": "Route not found."}), 404
    return jsonify(stops), 201


@dispatch_bp.put("/api/routes/<int:route_id>/stops/reorder")
def reorder_route_stops(route_id):
    payload = request.get_json(silent=True) or {}
    ordered_ids = payload.get("stop_ids") or []
    if not ordered_ids:
        return jsonify({"error": "Provide a 'stop_ids' array."}), 400
    dispatch_service.reorder_stops(route_id, ordered_ids)
    return jsonify({"ok": True})


@dispatch_bp.delete("/api/routes/<int:route_id>/stops/<int:stop_id>")
def remove_route_stop(route_id, stop_id):
    ok = dispatch_service.remove_stop(route_id, stop_id)
    if not ok:
        return jsonify({"error": "Stop not found."}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Drivers
# ------------------------------------------------------------------

@dispatch_bp.get("/api/drivers")
def list_drivers():
    branch = request.args.get("branch")
    drivers = dispatch_service.get_drivers(branch)
    return jsonify(drivers)


@dispatch_bp.post("/api/drivers")
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


@dispatch_bp.put("/api/drivers/<int:driver_id>")
def update_driver(driver_id):
    payload = request.get_json(silent=True) or {}
    driver = dispatch_service.update_driver(driver_id, **payload)
    if driver is None:
        return jsonify({"error": "Driver not found."}), 404
    return jsonify(driver)


@dispatch_bp.post("/api/drivers/seed-from-erp")
def seed_drivers():
    branch = request.args.get("branch")
    created = dispatch_service.seed_drivers_from_erp(branch)
    return jsonify({"created": len(created), "drivers": created})


# ------------------------------------------------------------------
# Truck Assignments
# ------------------------------------------------------------------

@dispatch_bp.get("/api/trucks")
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
    seen_ids = {v.get("id") or v.get("name") for v in vehicle_list}
    for a in assignments:
        if a["samsara_vehicle_id"] not in seen_ids:
            merged.append({
                "id": a["samsara_vehicle_id"],
                "name": a["samsara_vehicle_name"],
                "branch": a["branch_code"],
                "assignment": a,
            })

    return jsonify({"trucks": merged, "assignments": assignments})


@dispatch_bp.post("/api/trucks/assignments")
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


@dispatch_bp.put("/api/trucks/assignments/<int:assignment_id>")
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


@dispatch_bp.post("/api/trucks/assignments/copy-previous")
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

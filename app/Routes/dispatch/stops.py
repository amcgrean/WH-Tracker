from datetime import date
from flask import jsonify, request
from app.Routes.dispatch import dispatch_bp
from app.Routes.dispatch.helpers import (
    _add_business_days, _parse_iso_date, erp_service,
)


@dispatch_bp.get("/api/stops")
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


@dispatch_bp.get("/api/stops/enriched")
def enriched_stops():
    today = date.today()
    default_start = _add_business_days(today, -7)
    default_end = _add_business_days(today, 1)
    start = _parse_iso_date(request.args.get("start", default_start.isoformat()), default_start)
    end = _parse_iso_date(request.args.get("end", default_end.isoformat()), default_end)
    rows = erp_service.get_enriched_dispatch_stops(
        start=start,
        end=end,
        sale_types=request.args.get("sale_types"),
        status_filter=request.args.get("status"),
        route_id=request.args.get("route_id"),
        driver=request.args.get("driver"),
        include_no_gps=True,
        branches=request.args.get("branch"),
    )
    return jsonify(rows)


@dispatch_bp.get("/api/orders/<int:so_id>/lines")
def shipment_lines(so_id: int):
    shipment_num = request.args.get("shipment_num")
    shipment_value = int(shipment_num) if shipment_num not in (None, "", "null") else None
    lines = erp_service.get_dispatch_shipment_lines(so_id, shipment_value, limit=200)
    return jsonify(lines)


@dispatch_bp.get("/api/customers/<cust_key>/summary")
def customer_summary(cust_key):
    ar = erp_service.get_customer_ar_summary(cust_key)
    return jsonify(ar)


@dispatch_bp.get("/api/orders/<so_id>/timeline")
def order_timeline(so_id):
    events = erp_service.get_order_timeline(so_id)
    return jsonify(events)


@dispatch_bp.get("/api/orders/<so_id>/work-orders")
def order_work_orders(so_id):
    wos = erp_service.get_order_work_orders(so_id)
    return jsonify(wos)

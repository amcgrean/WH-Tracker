import csv
import io

from flask import Response, current_app, jsonify, render_template, request

from app.Routes.main import main_bp
from app.Services.delivery_reporting_service import DeliveryReportingService
from app.auth import role_required


@main_bp.route("/ops/delivery-reporting")
@role_required("ops", "manager")
def operations_delivery_reporting():
    return render_template("operations/delivery_reporting.html")


@main_bp.route("/api/ops/delivery-reporting")
@role_required("ops", "manager")
def api_operations_delivery_reporting():
    sale_type = request.args.get("sale_type", "all")
    detail_limit = request.args.get("detail_limit", default=250, type=int)

    try:
        payload = DeliveryReportingService().get_dashboard_payload(
            sale_type=sale_type,
            detail_limit=detail_limit,
        )
        return jsonify(payload)
    except Exception as exc:
        current_app.logger.exception("Delivery reporting API failed")
        return jsonify({
            "error": "Delivery reporting is temporarily unavailable.",
            "detail": str(exc),
        }), 500


@main_bp.route("/api/ops/delivery-reporting/export")
@role_required("ops", "manager")
def api_operations_delivery_reporting_export():
    sale_type = request.args.get("sale_type", "all")
    window = request.args.get("window", "30d")

    try:
        rows = DeliveryReportingService().get_export_rows(sale_type=sale_type, window=window)
    except Exception as exc:
        current_app.logger.exception("Delivery reporting export failed")
        return jsonify({
            "error": "Delivery reporting export is temporarily unavailable.",
            "detail": str(exc),
        }), 500

    output = io.StringIO()
    fieldnames = [
        "store",
        "ship_date",
        "so_id",
        "sale_type",
        "sale_type_group",
        "ship_via",
        "ship_via_bucket",
        "order_date",
        "order_time",
        "same_day_flag",
        "same_day_after_noon_flag",
        "shipped_line_count",
        "unique_item_count",
        "total_shipped_qty",
        "reference_piece_count",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    filename = f"delivery-report-{window}-{sale_type.replace(' ', '-').lower()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

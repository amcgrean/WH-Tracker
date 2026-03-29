import logging
from flask import render_template, request
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _get_branch, _get_rep_id, _normalize_daily_order, _normalize_top_customer,
    _normalize_status_breakdown, erp,
)

logger = logging.getLogger(__name__)


@sales_bp.route('/reports')
def reports():
    """Sales analytics and territory reports."""
    period_days = request.args.get('period', 30, type=int)
    branch = _get_branch()
    rep_id = _get_rep_id()
    try:
        report_data = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    except Exception as e:
        logger.error("Sales reports query failed: %s", e)
        report_data = {"daily_orders": [], "top_customers": [], "status_breakdown": []}
    daily_orders = [_normalize_daily_order(r) for r in report_data['daily_orders']]
    top_customers = [_normalize_top_customer(r) for r in report_data['top_customers']]
    status_breakdown = [_normalize_status_breakdown(r) for r in report_data['status_breakdown']]
    daily_labels = [r['expect_date'] for r in daily_orders]
    daily_values = [r['count'] for r in daily_orders]

    return render_template(
        'sales/reports.html',
        period_days=period_days,
        branch=branch,
        daily_orders=daily_orders,
        top_customers=top_customers,
        status_breakdown=status_breakdown,
        daily_labels=daily_labels,
        daily_values=daily_values,
        rep_id=rep_id,
    )

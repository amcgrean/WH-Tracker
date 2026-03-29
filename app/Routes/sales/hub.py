import logging
from flask import render_template, request, redirect, url_for
from sqlalchemy import desc
from app.Models.models import CustomerNote
from app.auth import get_current_user
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _get_branch, _get_rep_id, _normalize_order_row, _normalize_top_customer,
    _normalize_status_breakdown, erp,
)

logger = logging.getLogger(__name__)


@sales_bp.route('/')
@sales_bp.route('/hub')
def hub():
    """Personalized sales dashboard — orientation page and workspace launcher."""
    user = get_current_user()
    rep_id = _get_rep_id()
    branch = _get_branch()

    try:
        metrics = erp.get_sales_hub_metrics(rep_id=rep_id)
    except Exception as e:
        logger.error("Sales hub metrics failed: %s", e)
        metrics = {"open_orders_count": 0, "total_orders_today": 0}

    try:
        recent_orders = [
            _normalize_order_row(r) for r in erp.get_sales_order_status(
                rep_id=rep_id, limit=15, branch=branch,
            )
        ]
    except Exception as e:
        logger.error("Sales hub recent orders failed: %s", e)
        recent_orders = []

    try:
        recent_notes = CustomerNote.query.order_by(desc(CustomerNote.created_at)).limit(5).all()
    except Exception as e:
        logger.error("Sales hub recent notes failed: %s", e)
        recent_notes = []

    # Period-based report data (absorbed from rep_dashboard)
    period_days = request.args.get('period', 30, type=int)
    if period_days not in (7, 30, 90):
        period_days = 30

    try:
        reports = erp.get_sales_reports(period_days=period_days, branch=branch, rep_id=rep_id)
    except Exception as e:
        logger.error("Sales hub reports failed: %s", e)
        reports = {"top_customers": [], "status_breakdown": []}

    top_customers = [_normalize_top_customer(r) for r in reports.get('top_customers', [])]
    status_breakdown = [_normalize_status_breakdown(r) for r in reports.get('status_breakdown', [])]

    return render_template(
        'sales/hub.html',
        open_orders_count=metrics['open_orders_count'],
        total_orders_today=metrics['total_orders_today'],
        recent_orders=recent_orders,
        recent_notes=recent_notes,
        period_days=period_days,
        top_customers=top_customers,
        status_breakdown=status_breakdown,
        rep_id=rep_id,
        user=user,
    )


@sales_bp.route('/rep-dashboard')
def rep_dashboard():
    """Redirect legacy rep-dashboard URL to the hub."""
    return redirect(url_for('sales.hub', **request.args))

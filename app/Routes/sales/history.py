import logging
from flask import render_template, request, redirect, url_for
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _get_branch, _get_rep_id, _normalize_order_row, erp,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 50


@sales_bp.route('/history', defaults={'customer_number': ''})
@sales_bp.route('/history/<customer_number>')
def history(customer_number):
    """Historical purchase and pricing research workspace."""
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    page = request.args.get('page', 1, type=int)
    page = max(1, page)
    # Accept customer_number from URL path OR query param
    if not customer_number:
        customer_number = request.args.get('customer_number', '').strip()
    searched = bool(customer_number or q or date_from or date_to or status or branch)

    history_rows = []
    if searched:
        try:
            history_rows = [_normalize_order_row(r) for r in erp.get_sales_customer_orders(
                customer_number, q=q, date_from=date_from, date_to=date_to, status=status,
                branch=branch, limit=PAGE_SIZE, page=page, rep_id=rep_id,
            )]
        except Exception as e:
            logger.error("Purchase history query failed: %s", e)
            history_rows = []
    return render_template(
        'sales/history.html',
        history=history_rows,
        customer_number=customer_number,
        q=q, date_from=date_from, date_to=date_to, status=status, branch=branch,
        searched=searched,
        page=page,
        page_size=PAGE_SIZE,
        has_next=len(history_rows) == PAGE_SIZE,
        rep_id=rep_id,
    )


# Legacy URL redirect
@sales_bp.route('/order-history', defaults={'customer_number': ''})
@sales_bp.route('/order-history/<customer_number>')
def order_history(customer_number):
    args = dict(request.args)
    if customer_number:
        args['customer_number'] = customer_number
    return redirect(url_for('sales.history', **args))

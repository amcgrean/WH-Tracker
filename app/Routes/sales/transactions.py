import logging
from datetime import date, timedelta
from flask import render_template, request, redirect, url_for
from app.auth import get_current_user
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _get_branch, _get_rep_id, _normalize_order_row, erp,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 50

CLOSED_CM_STATUSES = ('I', 'C', 'X', 'CAN', 'CANCEL', 'CANCELED', 'CN', 'VOID')
# Sale types excluded from "delivery / add-on" view (leaves only delivery-style orders)
NON_DELIVERY_TYPES = ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD', 'CM')

VIEW_PRESETS = {
    'my_open_3d': {
        'label': 'My Open Orders', 'sublabel': 'Next 3 Days',
        'icon': 'fa-clock', 'color': 'success', 'section': 'my',
    },
    'my_open_7d': {
        'label': 'My Open Orders', 'sublabel': 'Next 7 Days',
        'icon': 'fa-calendar-week', 'color': 'primary', 'section': 'my',
    },
    'branch_delivery': {
        'label': 'Branch Orders', 'sublabel': 'Delivery / Add On',
        'icon': 'fa-truck', 'color': 'info', 'section': 'branch',
    },
    'branch_willcall': {
        'label': 'Branch Orders', 'sublabel': 'Will Call',
        'icon': 'fa-store', 'color': 'warning', 'section': 'branch',
    },
    'my_rma': {
        'label': 'My Open RMAs', 'sublabel': 'Credit Memos',
        'icon': 'fa-undo-alt', 'color': 'danger', 'section': 'my',
    },
    'my_shipped_2d': {
        'label': 'My Shipped', 'sublabel': 'Last 2 Days',
        'icon': 'fa-shipping-fast', 'color': 'teal', 'section': 'my',
    },
    'my_invoiced_5d': {
        'label': 'My Invoiced', 'sublabel': 'Last 5 Days',
        'icon': 'fa-file-invoice-dollar', 'color': 'secondary', 'section': 'my',
    },
}


def _get_user_rep_id():
    """Return the logged-in user's raw ERP rep ID (regardless of role)."""
    user = get_current_user()
    if not user:
        return ''
    return user.get('user_id', '') or ''


@sales_bp.route('/transactions')
def transactions():
    """Unified sales transaction workspace — search and act on all orders."""
    view = request.args.get('view', '').strip()
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    filter_salesperson = request.args.get('salesperson', '').strip()
    filter_customer = request.args.get('customer_code', '').strip()
    filter_shipto = request.args.get('shipto_seq', '').strip()
    branch = _get_branch()
    rep_id = _get_rep_id()
    user_rep_id = _get_user_rep_id()
    page = request.args.get('page', 1, type=int)
    page = max(1, page)
    my_orders = request.args.get('my_orders', '')
    today = date.today()

    # --- View presets override manual filters ---
    active_view = view if view in VIEW_PRESETS else ''
    sale_type = ''
    exclude_sale_types = ''
    use_shipment_query = False
    shipment_date_field = ''

    if active_view == 'my_open_3d':
        status = 'O'
        date_from = today.isoformat()
        date_to = (today + timedelta(days=3)).isoformat()
        rep_id = user_rep_id
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
    elif active_view == 'my_open_7d':
        status = 'O'
        date_from = today.isoformat()
        date_to = (today + timedelta(days=7)).isoformat()
        rep_id = user_rep_id
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
    elif active_view == 'branch_delivery':
        status = 'O'
        exclude_sale_types = ','.join(NON_DELIVERY_TYPES)
        rep_id = ''  # branch-wide, not filtered to user
    elif active_view == 'branch_willcall':
        status = 'O'
        sale_type = 'WILLCALL'
        rep_id = ''  # branch-wide
    elif active_view == 'my_rma':
        sale_type = 'CM'
        # Open CMs: exclude closed/cancelled statuses
        open_cm_statuses = [s for s in ('O', 'H') if len(s) == 1]
        status = ','.join(open_cm_statuses)
        date_from = ''
        date_to = ''
        rep_id = user_rep_id
    elif active_view == 'my_shipped_2d':
        use_shipment_query = True
        shipment_date_field = 'ship_date'
        date_from = (today - timedelta(days=2)).isoformat()
        date_to = today.isoformat()
        rep_id = user_rep_id
    elif active_view == 'my_invoiced_5d':
        use_shipment_query = True
        shipment_date_field = 'invoice_date'
        date_from = (today - timedelta(days=5)).isoformat()
        date_to = today.isoformat()
        rep_id = user_rep_id

    # Determine if we should filter to open only or show all statuses
    open_only = not active_view and not status and not date_from and not date_to and not q and not filter_salesperson and not filter_customer

    try:
        if use_shipment_query:
            orders = [
                _normalize_order_row(r, rep_id=user_rep_id) for r in erp.get_orders_by_shipment_date(
                    date_field=shipment_date_field,
                    date_from=date_from, date_to=date_to,
                    rep_id=rep_id, branch=branch, limit=PAGE_SIZE, page=page,
                )
            ]
        else:
            orders = [
                _normalize_order_row(r, rep_id=user_rep_id) for r in erp.get_sales_order_status(
                    q=q, limit=PAGE_SIZE, branch=branch, open_only=open_only,
                    rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
                    page=page, sale_type=sale_type, exclude_sale_types=exclude_sale_types,
                    customer_code=filter_customer, salesperson=filter_salesperson,
                    shipto_seq=filter_shipto,
                )
            ]
    except Exception as e:
        logger.error("Transactions query failed: %s", e)
        orders = []

    # Status counts for the summary bar
    status_counts = {}
    for o in orders:
        s = o.get('so_status', '')
        status_counts[s] = status_counts.get(s, 0) + 1

    return render_template(
        'sales/transactions.html',
        orders=orders,
        q=q,
        status=status if not active_view else '',
        date_from=date_from if not active_view else '',
        date_to=date_to if not active_view else '',
        filter_salesperson=filter_salesperson if not active_view else '',
        filter_customer=filter_customer if not active_view else '',
        filter_shipto=filter_shipto if not active_view else '',
        branch=branch,
        rep_id=rep_id,
        user_rep_id=user_rep_id,
        my_orders=my_orders,
        page=page,
        page_size=PAGE_SIZE,
        has_next=len(orders) == PAGE_SIZE,
        status_counts=status_counts,
        active_view=active_view,
        view_presets=VIEW_PRESETS,
    )


# Legacy URL redirects — old routes now served by /transactions
@sales_bp.route('/order-status')
def order_status():
    return redirect(url_for('sales.transactions', status='O', **{
        k: v for k, v in request.args.items() if k != 'status'
    }))


@sales_bp.route('/invoice-lookup')
def invoice_lookup():
    return redirect(url_for('sales.transactions', status='I,C', **{
        k: v for k, v in request.args.items() if k != 'status'
    }))

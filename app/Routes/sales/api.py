import logging
from flask import jsonify, request, url_for
from app.Routes.sales import sales_bp
from app.Routes.sales.helpers import (
    _get_branch, _get_rep_id, _normalize_order_row, _value, erp,
)

logger = logging.getLogger(__name__)


@sales_bp.route('/api/transactions')
def api_transactions():
    """JSON endpoint for transaction workspace — supports AJAX filtering."""
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    branch = _get_branch()
    rep_id = _get_rep_id()
    limit = min(int(request.args.get('limit', 100)), 500)
    page = request.args.get('page', 1, type=int)
    open_only = not status and not date_from and not date_to and not q
    try:
        orders = [
            _normalize_order_row(r) for r in erp.get_sales_order_status(
                q=q, limit=limit, branch=branch, open_only=open_only,
                rep_id=rep_id, status=status, date_from=date_from, date_to=date_to,
                page=page,
            )
        ]
    except Exception as e:
        logger.error("API transactions query failed: %s", e)
        orders = []
    return jsonify(orders)


# Keep old API endpoint working
@sales_bp.route('/api/orders')
def api_orders():
    """Legacy JSON endpoint — redirects to api_transactions."""
    return api_transactions()


@sales_bp.route('/api/salespeople')
def api_salespeople():
    """JSON endpoint for salesperson dropdown."""
    branch = _get_branch()
    try:
        rows = erp.get_distinct_salespeople(branch=branch)
    except Exception as e:
        logger.error("Salespeople list failed: %s", e)
        return jsonify([])
    return jsonify([{'id': r['rep_id'], 'label': r['rep_id']} for r in rows if r.get('rep_id')])


@sales_bp.route('/api/customers/list')
def api_customer_list():
    """JSON endpoint for customer dropdown — searches customers and ship-to addresses."""
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    try:
        rows = erp.get_sales_customers_search(q=q, limit=20)
    except Exception as e:
        logger.error("Customer list failed: %s", e)
        return jsonify([])
    results = []
    seen = set()
    for r in rows:
        key = _value(r, 'cust_code') or ''
        name = _value(r, 'cust_name') or key
        if key and key not in seen:
            seen.add(key)
            results.append({'id': key, 'label': f"{name} ({key})"})
    return jsonify(results)


@sales_bp.route('/api/customers/shipto/<customer_code>')
def api_customer_shipto(customer_code):
    """JSON endpoint for ship-to dropdown for a selected customer."""
    try:
        rows = erp.get_customer_ship_to_addresses(customer_code)
    except Exception as e:
        logger.error("Ship-to list failed for %s: %s", customer_code, e)
        return jsonify([])
    results = []
    for r in rows:
        seq = str(_value(r, 'seq_num', ''))
        name = _value(r, 'shipto_name', '')
        addr1 = _value(r, 'address_1', '')
        addr2 = _value(r, 'address_2', '')
        city = _value(r, 'city', '')
        label_parts = [p for p in [name, addr1, city] if p]
        label = f"#{seq} — {', '.join(label_parts)}" if label_parts else f"#{seq}"
        # search_text includes all fields for filtering
        search_text = ' '.join(str(p) for p in [seq, name, addr1, addr2, city] if p).lower()
        results.append({'id': seq, 'label': label, 'search': search_text})
    return jsonify(results)


@sales_bp.route('/api/customers/search')
def api_customer_search():
    """JSON endpoint for customer type-ahead."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        rows = erp.get_sales_customers_search(q=q, limit=10)
    except Exception as e:
        logger.error("Customer search failed: %s", e)
        return jsonify([])
    results = []
    seen = set()
    for r in rows:
        key = _value(r, 'cust_code') or ''
        name = _value(r, 'cust_name') or key
        if key and key not in seen:
            seen.add(key)
            results.append({
                'title': name,
                'subtitle': f"Customer # {key}",
                'url': url_for('sales.customer_profile', customer_number=key),
            })
    return jsonify(results)

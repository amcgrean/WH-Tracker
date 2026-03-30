import logging
from flask import request, session
from app.branch_utils import normalize_branch
from app.auth import get_current_user
from app.Services.erp_service import ERPService

logger = logging.getLogger(__name__)

erp = ERPService()


def _get_branch():
    """Read branch from URL param > session > empty (all branches)."""
    raw = request.args.get('branch', '').strip()
    if raw:
        return normalize_branch(raw) or ''
    return normalize_branch(session.get('selected_branch', '')) or ''


def _get_rep_id():
    """Return the logged-in user's ERP rep ID for filtering, or empty string.

    Sales-role users see their own orders by default.  Admin/ops users see all
    unless they explicitly opt in via ?my_orders=1.
    """
    user = get_current_user()
    if not user:
        return ''
    roles = set(user.get('roles') or [])
    # Admin/ops see everything unless they ask for "my orders"
    if roles & {'admin', 'ops'}:
        if request.args.get('my_orders', ''):
            return user.get('user_id', '') or ''
        return ''
    return user.get('user_id', '') or ''


def _value(row, key, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _format_timestamp(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%d %H:%M')
    return value or 'n/a'


def _format_date(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%d/%Y')
    return value or ''


def _normalize_order_row(row, rep_id=''):
    salesperson = _value(row, 'salesperson', '')
    order_writer = _value(row, 'order_writer', '')
    # Determine agent role relative to the logged-in user
    agent_role = ''
    if rep_id:
        is_agent1 = salesperson and salesperson == rep_id
        is_agent3 = order_writer and order_writer == rep_id
        if is_agent1 and is_agent3:
            agent_role = 'both'
        elif is_agent1:
            agent_role = 'acct_rep'
        elif is_agent3:
            agent_role = 'writer'
    return {
        'so_number': _value(row, 'so_number', ''),
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'address': _value(row, 'address', ''),
        'expect_date': _value(row, 'expect_date', ''),
        'expect_date_display': _format_date(_value(row, 'expect_date')),
        'ship_date': _value(row, 'ship_date', ''),
        'ship_date_display': _format_date(_value(row, 'ship_date')),
        'invoice_date': _value(row, 'invoice_date', ''),
        'invoice_date_display': _format_date(_value(row, 'invoice_date')),
        'reference': _value(row, 'reference', ''),
        'so_status': str(_value(row, 'so_status', '')).upper(),
        'handling_code': _value(row, 'handling_code', ''),
        'sale_type': str(_value(row, 'sale_type', '')).upper(),
        'ship_via': _value(row, 'ship_via', ''),
        'line_count': _value(row, 'line_count', 0),
        'salesperson': salesperson,
        'order_writer': order_writer,
        'agent_role': agent_role,
        'po_number': _value(row, 'po_number', ''),
        'synced_at': _value(row, 'synced_at'),
        'synced_at_display': _format_timestamp(_value(row, 'synced_at')),
    }


def _normalize_product_row(row):
    return {
        'item_number': _value(row, 'item_number', ''),
        'description': _value(row, 'description', ''),
        'quantity_on_hand': _value(row, 'quantity_on_hand', 0) or 0,
    }


def _normalize_top_customer(row):
    return {
        'customer_name': _value(row, 'customer_name', ''),
        'customer_code': _value(row, 'customer_code', ''),
        'order_count': _value(row, 'order_count', 0) or 0,
    }


def _normalize_status_breakdown(row):
    return {
        'so_status': _value(row, 'so_status', ''),
        'count': _value(row, 'count', 0) or 0,
    }


def _normalize_daily_order(row):
    expect_date = _value(row, 'expect_date', '')
    if hasattr(expect_date, 'strftime'):
        expect_date = expect_date.strftime('%Y-%m-%d')
    return {
        'expect_date': expect_date or '',
        'count': _value(row, 'count', 0) or 0,
    }

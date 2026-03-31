"""
po_service.py
-------------
ERP read-model queries for the PO Check-In module.

All functions here are read-only. They query:
  - app_po_search      — PO search view (must exist; apply sql/app_po_read_models.sql if missing)
  - app_po_header      — Full PO header detail
  - app_po_detail      — PO line items with resolved item codes
  - app_po_receiving_summary — Aggregated receiving data
  - erp_mirror_po_header    — Raw ERP PO table for open-PO lists

TRIM fix: joins on cust_key/seq_num always use TRIM(). For PO queries we join
on po_number and system_id — no TRIM needed for those columns.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, text

from app.extensions import db


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_purchase_orders(q: str, limit: int = 25) -> list[dict]:
    """Search app_po_search view by po_number, supplier_name, or reference.

    Returns up to *limit* (max 25) rows as JSON-serializable dicts.
    """
    q_like = f"%{q}%"
    sql = text("""
        SELECT po_number, po_id, supplier_name, supplier_code, system_id,
               expect_date, order_date, po_status, receipt_count
        FROM app_po_search
        WHERE po_number ILIKE :q
           OR supplier_name ILIKE :q
           OR reference ILIKE :q
        ORDER BY po_number
        LIMIT :limit
    """)
    rows = db.session.execute(sql, {"q": q_like, "limit": min(limit, 25)}).mappings().all()
    return [_serialize_row(r) for r in rows]


def list_open_pos_for_branch(branch_code: Optional[str], limit: int = 500) -> list[dict]:
    """Return open POs for a branch/system (or all branches when branch_code is None).

    "Open" means po_status (case-insensitive) NOT IN
    ('closed', 'complete', 'cancelled', 'void', 'received').
    Uses app_po_search view and scopes on system_id.
    """
    open_filter = (
        "UPPER(COALESCE(po_status, '')) NOT IN "
        "('CLOSED', 'COMPLETE', 'CANCELLED', 'CANCELED', 'VOID', 'RECEIVED')"
    )

    if branch_code:
        from app.branch_utils import expand_branch
        codes = expand_branch(branch_code)
        sql = text(f"""
            SELECT po_number, supplier_name, supplier_code, system_id,
                   expect_date, order_date, po_status, receipt_count
            FROM app_po_search
            WHERE system_id = ANY(:codes)
              AND {open_filter}
            ORDER BY expect_date ASC NULLS LAST
            LIMIT :limit
        """)
        rows = db.session.execute(sql, {"codes": codes, "limit": limit}).mappings().all()
    else:
        sql = text(f"""
            SELECT po_number, supplier_name, supplier_code, system_id,
                   expect_date, order_date, po_status, receipt_count
            FROM app_po_search
            WHERE {open_filter}
            ORDER BY expect_date ASC NULLS LAST
            LIMIT :limit
        """)
        rows = db.session.execute(sql, {"limit": limit}).mappings().all()

    return [_serialize_row(r) for r in rows]


def get_purchase_order(po_number: str) -> Optional[dict]:
    """Fetch PO header + line items + receiving summary.

    Returns ``{"header": {...}, "lines": [...], "receiving_summary": {...}}``
    or ``None`` if the PO is not found.
    """
    header_sql = text("""
        SELECT * FROM app_po_header
        WHERE po_number = :po_number
        LIMIT 1
    """)
    header_row = db.session.execute(header_sql, {"po_number": po_number}).mappings().first()
    if not header_row:
        return None

    lines_sql = text("""
        SELECT * FROM app_po_detail
        WHERE po_number = :po_number
        ORDER BY line_number ASC
    """)
    lines_rows = db.session.execute(lines_sql, {"po_number": po_number}).mappings().all()

    receiving_sql = text("""
        SELECT * FROM app_po_receiving_summary
        WHERE po_number = :po_number
        LIMIT 1
    """)
    receiving_row = db.session.execute(receiving_sql, {"po_number": po_number}).mappings().first()

    return {
        "header": _serialize_row(header_row),
        "lines": [_serialize_row(r) for r in lines_rows],
        "receiving_summary": _serialize_row(receiving_row) if receiving_row else None,
    }


def get_submission_summary_for_pos(po_numbers: list[str]) -> dict[str, int]:
    """Return {po_number: submission_count} for a list of PO numbers.

    Used on the open-PO list to show how many check-ins exist per PO.
    """
    if not po_numbers:
        return {}
    from app.Models.models import POSubmission
    rows = (
        db.session.query(POSubmission.po_number, func.count(POSubmission.id))
        .filter(POSubmission.po_number.in_(po_numbers))
        .group_by(POSubmission.po_number)
        .all()
    )
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_row(row) -> dict:
    """Convert a SQLAlchemy RowMapping to a JSON-serializable dict."""
    if row is None:
        return {}
    result = {}
    for k, v in dict(row).items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, Decimal):
            result[k] = float(v)
        else:
            result[k] = v
    return result

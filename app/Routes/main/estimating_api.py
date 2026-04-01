"""
Estimating integration routes
==============================
Supports the beisser-takeoff → LiveEdge merge.

Routes
------
GET  /estimating              Redirect to ESTIMATING_APP_URL (nav link target).
GET  /api/health              Full health check: DB ping + version.  Used by
                              Cloudflare health checks and monitoring.
GET  /api/customers/search    ERP customer search for the estimating app.
                              Requires a valid session OR X-Api-Key header
                              matching INTERNAL_API_KEY.

Customer search response
------------------------
GET /api/customers/search?q=<term>&branch=<branch_code>&limit=<int>

  {
    "customers": [
      {
        "code":   "ACME",
        "name":   "Acme Hardware",
        "city":   "Grimes",      // from primary ship-to (seq_num='0'); may be null
        "state":  "IA",          // from primary ship-to; may be null
        "branch": "20GR"
      },
      ...
    ]
  }

city/state come from erp_mirror_cust_shipto where seq_num = '0' (the primary
bill-to address).  They are null when no seq_num='0' record exists.

Requires central_db_mode (PostgreSQL mirror).  If the ERP mirror is
unavailable, returns an empty list with a 200 so callers degrade gracefully.

File attachment support (no code changes needed)
-------------------------------------------------
The polymorphic File/FileVersion models use free-text entity_type.  To attach
files to bids or designs from the estimating app, POST to:

  POST /files/upload
  Content-Type: multipart/form-data

  Fields:
    file          (required) — the file binary
    entity_type   (required) — "bid" or "design"
    entity_id     (required) — bid/design identifier string
    category      (optional) — e.g. "plan", "quote", "markup"
    change_note   (optional) — version note

  Returns JSON: { "id": <file_id>, "key": "<r2_object_key>", ... }

Retrieve:
  GET  /files/<id>           → redirect to presigned R2 URL
  GET  /files/<id>/info      → JSON metadata + version history
  GET  /files/entity/bid/<id>   → list all files for a bid
  DELETE /files/<id>         → soft-delete
"""

import logging
import os

from flask import current_app, jsonify, redirect, request
from sqlalchemy import text

from app.auth import is_authenticated
from app.extensions import db
from app.Routes.main import main_bp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estimating redirect — target for the nav link
# ---------------------------------------------------------------------------

@main_bp.get('/estimating')
def estimating_redirect():
    """Redirect to the estimating app.  URL is set via ESTIMATING_APP_URL."""
    url = current_app.config.get('ESTIMATING_APP_URL') or '#'
    if url == '#':
        # App not yet deployed — fall back to work center
        return redirect('/work_center')
    return redirect(url)


# ---------------------------------------------------------------------------
# /api/health — full readiness check
# ---------------------------------------------------------------------------

@main_bp.get('/api/health')
def api_health():
    """
    Full health / readiness check.

    Response: { "status": "ok"|"degraded", "version": "<sha>", "db": "ok"|"error" }

    - version  — GIT_SHA env var (set by Fly build), then FLY_APP_VERSION,
                 then "dev"
    - db       — result of a trivial SELECT 1 against the app database
    - status   — "ok" iff db is "ok"; "degraded" otherwise

    This endpoint is public (no auth required) so Cloudflare and external
    monitors can reach it without a session.
    """
    version = (
        os.environ.get('GIT_SHA')
        or os.environ.get('FLY_APP_VERSION')
        or 'dev'
    )

    db_status = 'ok'
    try:
        db.session.execute(text('SELECT 1'))
    except Exception as exc:
        logger.error('Health check DB ping failed: %s', exc)
        db_status = 'error'

    return jsonify({
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'version': version,
        'db': db_status,
    })


# ---------------------------------------------------------------------------
# /api/customers/search — ERP customer lookup for the estimating app
# ---------------------------------------------------------------------------

def _check_api_auth() -> bool:
    """Return True if the request is authenticated via session or API key."""
    if is_authenticated():
        return True
    api_key = request.headers.get('X-Api-Key', '')
    internal_key = current_app.config.get('INTERNAL_API_KEY', '')
    return bool(internal_key and api_key == internal_key)


@main_bp.get('/api/customers/search')
def api_customers_search():
    """
    ERP customer search — for use by the estimating app.

    Query params:
      q       (required, min 2 chars) — search term matched against cust_code
                and cust_name (case-insensitive)
      branch  (optional) — filter by branch_code (e.g. "20GR")
      limit   (optional, default 20, max 100)

    Auth: valid session cookie OR X-Api-Key: <INTERNAL_API_KEY>

    Returns 200 { customers: [...] } always (empty list on error/no results).
    Returns 401 if neither auth method succeeds.
    Returns 400 if q is missing or too short.

    Requires PostgreSQL mirror (central_db_mode).  Returns [] when ERP data
    is unavailable.
    """
    if not _check_api_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'error': 'q must be at least 2 characters'}), 400

    branch = request.args.get('branch', '').strip().upper() or None
    limit = min(int(request.args.get('limit', 20)), 100)

    try:
        params: dict = {'q': f'%{q}%', 'limit': limit}
        branch_clause = ''
        if branch:
            branch_clause = 'AND UPPER(COALESCE(c.branch_code, \'\')) = :branch'
            params['branch'] = branch

        rows = db.session.execute(
            text(f"""
                SELECT
                    c.cust_code,
                    c.cust_name,
                    c.branch_code,
                    cs.city,
                    cs.state
                FROM erp_mirror_cust c
                LEFT JOIN erp_mirror_cust_shipto cs
                       ON cs.cust_key = c.cust_key
                      AND cs.seq_num  = '0'
                      AND cs.is_deleted = false
                WHERE c.is_deleted = false
                  AND (
                      c.cust_code ILIKE :q
                      OR c.cust_name ILIKE :q
                  )
                  {branch_clause}
                ORDER BY c.cust_name
                LIMIT :limit
            """),
            params,
        ).fetchall()

        customers = [
            {
                'code':   row.cust_code,
                'name':   row.cust_name or '',
                'city':   row.city or '',
                'state':  row.state or '',
                'branch': row.branch_code or '',
            }
            for row in rows
        ]
    except Exception as exc:
        logger.error('Customer search failed: %s', exc)
        customers = []

    return jsonify({'customers': customers})

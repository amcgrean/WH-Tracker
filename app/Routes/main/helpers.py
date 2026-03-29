import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytz
from flask import request, session

from app.branch_utils import normalize_branch, branch_label, is_valid_branch
from app.extensions import db
from app.Models.models import PickTypes, ERPSyncState


# ── Pick type constants ───────────────────────────────────────────────────────
WILL_CALL_TYPE_ID = 6
CHUNK_SIZE = 900  # SQL Server IN-clause variable limit

DEFAULT_PICK_TYPES = {
    1: 'Yard',
    2: 'Door 1',
    3: 'Decking',
    4: 'EWP',
    5: 'Millwork',
    WILL_CALL_TYPE_ID: 'Will Call',
}

# Maps ERP handling_code (uppercase) to pick_type_id for smart scan auto-detection.
HANDLING_CODE_TO_PICK_TYPE = {
    'DECK BLDG': 3,   # Decking
    'DECKING':   3,
    'DOOR1':     2,    # Door 1
    'DOOR 1':    2,
    'EWP':       4,    # EWP
    'MILLWORK':  5,    # Millwork
    'METALS':    1,    # Yard (metals picked from yard)
}

# Upload extensions for credit images
ALLOWED_UPLOAD_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.tiff', '.tif'}


def _get_branch():
    """Read branch from URL param > session > None (all branches)."""
    raw = request.args.get('branch', '').strip()
    if raw:
        return normalize_branch(raw) or None
    return normalize_branch(session.get('selected_branch', '')) or None


def pick_type_from_handling_code(handling_code):
    """Return the pick_type_id for an ERP handling_code, defaulting to Yard (1)."""
    if not handling_code:
        return 1
    return HANDLING_CODE_TO_PICK_TYPE.get(handling_code.strip().upper(), 1)


def ensure_pick_type_exists(pick_type_id):
    """Return a PickTypes row for the requested ID, creating defaults when missing."""
    pick_type = db.session.get(PickTypes, pick_type_id)
    if pick_type:
        return pick_type

    type_name = DEFAULT_PICK_TYPES.get(pick_type_id)
    if not type_name:
        return None

    pick_type = PickTypes(pick_type_id=pick_type_id, type_name=type_name)
    db.session.add(pick_type)
    db.session.flush()
    return pick_type


def get_pick_type_name(pick_type_id):
    return DEFAULT_PICK_TYPES.get(pick_type_id, 'Unknown')


def localize_to_cst(naive_utc_datetime):
    utc_zone = pytz.timezone('UTC')
    cst_zone = pytz.timezone('America/Chicago')

    # Check if the datetime object is naive before localizing
    if naive_utc_datetime.tzinfo is None or naive_utc_datetime.tzinfo.utcoffset(naive_utc_datetime) is None:
        utc_datetime = utc_zone.localize(naive_utc_datetime)
    else:
        utc_datetime = naive_utc_datetime

    cst_datetime = utc_datetime.astimezone(cst_zone)
    return cst_datetime


def calculate_business_elapsed_time(start_time, end_time=None):
    BUSINESS_START = 7  # 7 AM
    BUSINESS_END = 17   # 5 PM
    start_time_cst = localize_to_cst(start_time)
    end_time_cst = localize_to_cst(end_time if end_time else datetime.utcnow())
    elapsed = timedelta()
    current = start_time_cst
    while current < end_time_cst:
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = current.replace(hour=BUSINESS_END, minute=0, second=0, microsecond=0)
        start_of_day = current.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
        if current.hour < BUSINESS_START:
            current = start_of_day
        elif current.hour < BUSINESS_END:
            if end_time_cst < end_of_day:
                elapsed += end_time_cst - current
                break
            else:
                elapsed += end_of_day - current
                current = next_day
        else:
            current = next_day
    return elapsed  # Return the timedelta object directly


def format_elapsed_time(start_time, end_time=None):
    """Return business-hours elapsed time as a human-readable string (e.g. '2h 15m')."""
    elapsed = calculate_business_elapsed_time(start_time, end_time)
    total_seconds = int(elapsed.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def upsert_sync_state(payload):
    worker_name = str(payload.get('worker_name') or 'erp-sync').strip() or 'erp-sync'
    state = ERPSyncState.query.filter_by(worker_name=worker_name).first()
    if not state:
        state = ERPSyncState(worker_name=worker_name)
        db.session.add(state)

    state.worker_mode = payload.get('worker_mode') or state.worker_mode or 'pi'
    state.source_mode = payload.get('source_mode') or state.source_mode or 'local_sql'
    state.target_mode = payload.get('target_mode') or state.target_mode or 'mirror'
    state.interval_seconds = int(payload.get('interval_seconds') or state.interval_seconds or 5)
    state.change_monitoring = bool(payload.get('change_monitoring', state.change_monitoring))
    state.last_status = payload.get('status') or state.last_status or 'running'
    state.last_error = payload.get('last_error')
    state.last_change_token = payload.get('last_change_token')
    state.last_payload_hash = payload.get('last_payload_hash')
    state.last_push_reason = payload.get('last_push_reason')

    counts = payload.get('counts')
    if counts is not None:
        state.last_counts_json = json.dumps(counts)

    now = datetime.utcnow()
    state.last_heartbeat_at = now
    if state.last_status in ('success', 'noop'):
        state.last_success_at = now
    if state.last_status == 'error':
        state.last_error_at = now

    return state


def parse_sync_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def parse_sync_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).split('T')[0]).date()
    except Exception:
        return None


def parse_selected_work_order_payload(raw_value):
    if not raw_value:
        return None

    try:
        payload = json.loads(raw_value)
        if isinstance(payload, dict):
            return {
                'wo_id': str(payload.get('wo_id') or '').strip(),
                'so_number': str(payload.get('so_number') or '').strip(),
                'item_number': str(payload.get('item_number') or '').strip(),
                'description': str(payload.get('description') or '').strip(),
            }
    except Exception:
        pass

    parts = str(raw_value).split('|', 3)
    if len(parts) == 4:
        wo_id, so_number, item_number, description = parts
    elif len(parts) == 3:
        wo_id, item_number, description = parts
        so_number = ''
    else:
        return None

    return {
        'wo_id': str(wo_id).strip(),
        'so_number': str(so_number).strip(),
        'item_number': str(item_number).strip(),
        'description': str(description).strip(),
    }


def credit_upload_dir():
    """Return the absolute path to the credits upload folder."""
    base = os.environ.get('UPLOAD_FOLDER', 'uploads/credits')
    if not os.path.isabs(base):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), base)
    return base


def _kiosk_context(branch_code):
    """Common template context for kiosk pages."""
    from flask import abort
    normalized = normalize_branch(branch_code)
    if not normalized or not is_valid_branch(normalized):
        abort(404, f"Unknown branch: {branch_code}")
    return {
        "kiosk_branch": normalized,
        "kiosk_branch_label": branch_label(normalized),
    }


def _tv_context(branch_code):
    """Common template context for TV pages."""
    from flask import abort
    normalized = normalize_branch(branch_code)
    if not normalized or not is_valid_branch(normalized):
        abort(404, f"Unknown branch: {branch_code}")
    return {
        "tv_branch": normalized,
        "tv_branch_label": branch_label(normalized),
    }

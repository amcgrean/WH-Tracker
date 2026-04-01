"""PO blueprint helpers — shared across sub-modules."""
from __future__ import annotations

import re

from flask import session

from app.auth import SESSION_USER_BRANCH, SESSION_USER_ROLES
from app.Models.models import POSubmission


def _current_branch() -> str:
    return session.get(SESSION_USER_BRANCH) or ""


def _user_roles() -> set:
    return set(session.get(SESSION_USER_ROLES, []))


def _submission_scope_branch(user_roles: set, user_branch: str) -> str | None:
    """Return the branch to scope submissions queries to, or None for all branches."""
    if "admin" in user_roles or "supervisor" in user_roles:
        return None
    return user_branch or None


def _sanitize_po(po_number: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", po_number)


def _sub_to_dict(sub: POSubmission) -> dict:
    return {
        "id": sub.id,
        "po_number": sub.po_number,
        "image_urls": sub.image_urls or [],
        "thumbnail": (sub.image_urls or [None])[0],
        "supplier_name": sub.supplier_name,
        "supplier_key": sub.supplier_key,
        "po_status": sub.po_status,
        "submission_type": sub.submission_type,
        "priority": sub.priority,
        "queue_item_id": sub.queue_item_id,
        "notes": sub.notes,
        "status": sub.status,
        "submitted_by": sub.submitted_by,
        "submitted_username": sub.submitted_username,
        "branch": sub.branch,
        "reviewer_notes": sub.reviewer_notes,
        "reviewed_by": sub.reviewed_by,
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }

"""
auth.py
-------
Helpers, decorators, and session utilities for the WH-Tracker auth layer.

Usage in route files:
    from app.auth import login_required, role_required, get_current_user

    @main.route('/some-route')
    @login_required
    def some_route():
        ...

    @main.route('/admin-only')
    @role_required('admin')
    def admin_only():
        ...
"""

from functools import wraps

from flask import abort, redirect, request, session, url_for


# ---------------------------------------------------------------------------
# Session keys (single source of truth)
# ---------------------------------------------------------------------------
SESSION_USER_ID       = "user_id"        # AppUser.id (int)
SESSION_USER_EMAIL    = "user_email"     # e.g. "mschmit@beisserlumber.com"
SESSION_USER_REP_ID   = "user_rep_id"   # ERP rep/employee ID e.g. "mschmit"
SESSION_USER_NAME     = "user_display_name"
SESSION_USER_ROLES    = "user_roles"     # list[str] — used by navigation.py


# ---------------------------------------------------------------------------
# Current-user accessor
# ---------------------------------------------------------------------------

def get_current_user() -> dict | None:
    """
    Return a dict of the logged-in user's session data, or None if not authenticated.

    Keys: id, email, user_id (rep_id), display_name, roles
    """
    uid = session.get(SESSION_USER_ID)
    if not uid:
        return None
    return {
        "id":           uid,
        "email":        session.get(SESSION_USER_EMAIL, ""),
        "user_id":      session.get(SESSION_USER_REP_ID, ""),   # ERP rep ID
        "display_name": session.get(SESSION_USER_NAME, ""),
        "roles":        session.get(SESSION_USER_ROLES, []),
    }


def is_authenticated() -> bool:
    return bool(session.get(SESSION_USER_ID))


def _user_has_role(*roles: str) -> bool:
    user_roles = set(session.get(SESSION_USER_ROLES, []))
    return "admin" in user_roles or bool(user_roles & set(roles))


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    """Redirect to login if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles: str):
    """
    Decorator factory. User must be authenticated AND hold at least one of
    the listed roles (admins always pass).

    Example:
        @role_required("admin", "ops")
        def my_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not is_authenticated():
                return redirect(url_for("auth.login", next=request.url))
            if not _user_has_role(*roles):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

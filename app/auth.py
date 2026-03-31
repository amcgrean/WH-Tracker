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


ROLE_PERMISSIONS = {
    "purchasing": {
        "purchasing.dashboard.view",
        "purchasing.branch.view",
        "purchasing.queue.view",
        "purchasing.po.review",
        "purchasing.receiving.resolve",
    },
    "manager": {
        "purchasing.dashboard.view",
        "purchasing.branch.view",
        "purchasing.all_branches.view",
        "purchasing.queue.view",
        "purchasing.queue.assign",
        "purchasing.po.review",
        "purchasing.po.approve",
        "purchasing.receiving.resolve",
    },
    "ops": {
        "purchasing.dashboard.view",
        "purchasing.branch.view",
        "purchasing.all_branches.view",
        "purchasing.queue.view",
        "purchasing.queue.assign",
        "purchasing.po.review",
        "purchasing.po.approve",
        "purchasing.receiving.resolve",
    },
    "supervisor": {
        "purchasing.dashboard.view",
        "purchasing.branch.view",
        "purchasing.all_branches.view",
        "purchasing.queue.view",
        "purchasing.queue.assign",
        "purchasing.po.review",
        "purchasing.po.approve",
        "purchasing.receiving.resolve",
    },
    "warehouse": {
        "purchasing.dashboard.view",
        "purchasing.branch.view",
        "po.submit",
    },
}


# ---------------------------------------------------------------------------
# Session keys (single source of truth)
# ---------------------------------------------------------------------------
SESSION_USER_ID       = "user_id"        # AppUser.id (int)
SESSION_USER_EMAIL    = "user_email"     # e.g. "mschmit@beisserlumber.com"
SESSION_USER_REP_ID   = "user_rep_id"   # ERP rep/employee ID e.g. "mschmit"
SESSION_USER_NAME     = "user_display_name"
SESSION_USER_ROLES    = "user_roles"     # list[str] — used by navigation.py
SESSION_USER_BRANCH   = "user_branch"   # AppUser.branch e.g. "20GR" — used by PO module


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
        "branch":       session.get(SESSION_USER_BRANCH, ""),
    }


def is_authenticated() -> bool:
    return bool(session.get(SESSION_USER_ID))


def _user_has_role(*roles: str) -> bool:
    user_roles = set(session.get(SESSION_USER_ROLES, []))
    return "admin" in user_roles or bool(user_roles & set(roles))


def get_current_user_permissions() -> set[str]:
    user_roles = set(session.get(SESSION_USER_ROLES, []))
    if "admin" in user_roles:
        return {"*"}

    permissions: set[str] = set()
    for role in user_roles:
        permissions.update(ROLE_PERMISSIONS.get(role, set()))
    return permissions


def user_has_permission(*permissions: str) -> bool:
    granted = get_current_user_permissions()
    if "*" in granted:
        return True
    return any(permission in granted for permission in permissions)


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


def permission_required(*permissions: str):
    """Require the user to hold at least one mapped permission."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not is_authenticated():
                return redirect(url_for("auth.login", next=request.url))
            if not user_has_permission(*permissions):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

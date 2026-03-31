from flask import Blueprint, redirect, request, url_for

dispatch_bp = Blueprint("dispatch", __name__, url_prefix="/dispatch")

from app.Routes.dispatch import board, stops, api, planning  # noqa: E402, F401


@dispatch_bp.before_request
def _require_login():
    from app.auth import is_authenticated
    if not is_authenticated():
        return redirect(url_for("auth.login", next=request.url))

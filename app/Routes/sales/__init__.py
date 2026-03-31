from flask import Blueprint, redirect, request, url_for

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')

from app.Routes.sales import hub, transactions, customers, history, reports, api  # noqa: E402, F401


@sales_bp.before_request
def _require_login():
    from app.auth import is_authenticated
    if not is_authenticated():
        return redirect(url_for("auth.login", next=request.url))

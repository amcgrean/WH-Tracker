from flask import Blueprint

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')

from app.Routes.sales import hub, transactions, customers, history, reports, api  # noqa: E402, F401

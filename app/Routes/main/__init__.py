from flask import Blueprint

main_bp = Blueprint('main', __name__)

from app.Routes.main import (  # noqa: E402, F401
    health,
    picks,
    work_orders,
    warehouse,
    delivery,
    credits,
    search,
    supervisor,
    kiosk,
    tv,
    api,
)

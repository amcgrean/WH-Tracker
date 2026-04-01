from flask import Blueprint

purchasing_bp = Blueprint("purchasing", __name__, url_prefix="/purchasing")

from app.Routes.purchasing import views, api  # noqa: E402, F401

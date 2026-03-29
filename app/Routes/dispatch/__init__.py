from flask import Blueprint

dispatch_bp = Blueprint("dispatch", __name__, url_prefix="/dispatch")

from app.Routes.dispatch import board, stops, api  # noqa: E402, F401

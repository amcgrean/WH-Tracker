from flask import Blueprint

po_bp = Blueprint("po", __name__, url_prefix="/po")

from app.Routes.po import checkin, review, open_pos, api  # noqa: E402, F401

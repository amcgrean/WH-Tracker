from flask import jsonify
from app.Routes.main import main_bp


@main_bp.get("/healthz")
def root_health():
    return jsonify({"ok": True, "service": "wh-tracker"})

from flask import Blueprint, redirect, request, url_for

main_bp = Blueprint('main', __name__)

from app.Routes.main import (  # noqa: E402, F401
    health,
    picks,
    work_orders,
    warehouse,
    delivery,
    operations,
    credits,
    search,
    supervisor,
    kiosk,
    tv,
    api,
)


@main_bp.before_request
def _require_login():
    public_paths = {"/pick_tracker", "/api/smart_scan"}
    public_path_prefixes = (
        "/kiosk/",
        "/tv/",
        "/confirm_picker/",
        "/input_pick/",
        "/complete_pick/",
        "/start_pick/",
    )
    # Health check, kiosk, TV, and the legacy pick-tracker flow are exempt.
    if request.endpoint == "main.root_health":
        return
    if request.path in public_paths or request.path.startswith(public_path_prefixes):
        return
    from app.auth import is_authenticated
    if not is_authenticated():
        return redirect(url_for("auth.login", next=request.url))

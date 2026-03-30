import os

from flask import Flask
from flask_migrate import upgrade
from .extensions import db, migrate
from .Models.models import AppUser, CreditImage, CustomerNote, ERPMirrorArOpen, ERPMirrorArOpenDetail, ERPMirrorCustomer, ERPMirrorCustomerShipTo, ERPMirrorItem, ERPMirrorItemBranch, ERPMirrorItemUomConv, ERPMirrorPickDetailNormalized, ERPMirrorPickHeaderNormalized, ERPMirrorPrintTransaction, ERPMirrorPrintTransactionDetail, ERPMirrorSalesOrderHeader, ERPMirrorSalesOrderLine, ERPMirrorShipmentHeader, ERPMirrorShipmentLine, ERPSyncBatch, ERPSyncState, ERPSyncTableState, File, FileVersion, OTPCode, Pick, PickAssignment, PickTypes, Pickster, POSubmission, WorkOrder, WorkOrderAssignment  # noqa: F401
from .Models.dispatch_models import DispatchRoute, DispatchRouteStop, DispatchDriver, DispatchTruckAssignment  # noqa: F401
from .Routes.main import main_bp as main_blueprint
from .Routes.dispatch import dispatch_bp as dispatch_blueprint
from .Routes.sales import sales_bp as sales_blueprint
from .Routes.auth import auth_bp as auth_blueprint
from .Routes.files import files as files_blueprint
from .Routes.po_routes import po_bp as po_blueprint
from .runtime_settings import env_bool, is_fly_runtime
from .navigation import build_navigation, get_current_user_roles
from .auth import get_current_user
from .branch_utils import normalize_branch, sidebar_branch_choices, branch_label, expand_branch


def _resolve_branched_alembic_state(app):
    """
    Resolve a branched alembic_version state where multiple overlapping
    revision IDs exist in the table.  Keeps only the true head(s) and
    removes ancestor revisions so that the next upgrade() call succeeds.
    """
    from sqlalchemy import text
    from alembic.script import ScriptDirectory
    from alembic.config import Config as AlembicConfig

    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        versions = [r[0] for r in rows]
    except Exception as e:
        app.logger.error(f"Could not read alembic_version: {e}")
        return

    if len(versions) <= 1:
        return  # Nothing to resolve

    app.logger.warning(
        f"Branched alembic_version detected with {len(versions)} rows: {versions}. "
        "Removing ancestor revisions."
    )

    try:
        migrations_dir = app.extensions["migrate"].directory
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", migrations_dir)
        script_dir = ScriptDirectory.from_config(alembic_cfg)

        version_set = set(versions)
        ancestors: set = set()
        for v in versions:
            try:
                # Walk the ancestry chain of v; any sibling version we encounter
                # is an ancestor (and therefore not a true head).
                for anc_rev in script_dir.iterate_revisions(v, None):
                    if anc_rev.revision != v and anc_rev.revision in version_set:
                        ancestors.add(anc_rev.revision)
            except Exception:
                continue

        if not ancestors:
            app.logger.error("Could not identify ancestor revisions; manual DB intervention required.")
            return

        with db.engine.connect() as conn:
            for v in ancestors:
                conn.execute(
                    text("DELETE FROM alembic_version WHERE version_num = :v"),
                    {"v": v},
                )
            conn.commit()
        app.logger.info(f"Removed ancestor revision(s) {ancestors} from alembic_version.")
    except Exception as e:
        app.logger.error(f"Failed to resolve branched alembic state: {e}")


def _run_migrations(app):
    """Run pending Alembic migrations, recovering from branched-state errors.

    Uses a PostgreSQL advisory lock so that only one Fly machine runs
    migrations at a time — the others skip and let the winner handle DDL.
    """
    from sqlalchemy import text

    # Try to grab an advisory lock (non-blocking).  If another machine
    # already holds it we simply skip migrations on this instance.
    MIGRATION_LOCK_ID = 7483201  # arbitrary but fixed
    lock_acquired = False
    try:
        with db.engine.connect() as conn:
            result = conn.execute(
                text("SELECT pg_try_advisory_lock(:id)"),
                {"id": MIGRATION_LOCK_ID},
            )
            lock_acquired = result.scalar()
    except Exception:
        # Non-PostgreSQL (e.g. SQLite in dev) — just proceed without locking.
        lock_acquired = True

    if not lock_acquired:
        app.logger.info("Another machine holds the migration lock — skipping migrations.")
        return

    try:
        upgrade()
        return
    except SystemExit:
        # flask_migrate calls sys.exit(1) on alembic errors; catch it so the
        # serverless function does not crash on a recoverable migration failure.
        pass
    except Exception as e:
        app.logger.error(f"Migration error: {e}")
        return

    # First attempt failed – try to resolve a branched alembic_version table
    # (e.g. two rows like 83fabbe397a1 + d1e2f3a4b5c6 which overlap on the
    # same linear chain) then retry.
    _resolve_branched_alembic_state(app)

    try:
        upgrade()
    except (SystemExit, Exception) as e:
        app.logger.error(f"Migration upgrade failed after recovery attempt: {e}")


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    # Initialize other extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # Register Blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(dispatch_blueprint)
    app.register_blueprint(sales_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(files_blueprint)
    app.register_blueprint(po_blueprint)

    @app.context_processor
    def inject_navigation():
        from flask import request, session
        current_roles = get_current_user_roles()

        # Branch precedence: URL param > session > None
        raw_branch = request.args.get("branch") or session.get("selected_branch") or ""
        selected_branch = normalize_branch(raw_branch)

        return {
            "nav_sections": build_navigation(current_roles),
            "current_user_roles": current_roles,
            "current_user": get_current_user(),
            "selected_branch": selected_branch,
            "selected_branch_label": branch_label(selected_branch),
            "branch_choices": sidebar_branch_choices(),
        }

    @app.before_request
    def make_session_permanent():
        from flask import session
        session.permanent = True

    @app.before_request
    def enforce_auth():
        """
        When AUTH_REQUIRED=true every route except the auth blueprint and static
        files redirects unauthenticated visitors to the login page.
        """
        if not app.config.get("AUTH_REQUIRED"):
            return
        from flask import redirect, request, session, url_for
        public_endpoints = {
            "auth.login",
            "auth.verify",
            "auth.resend",
            "static",
            "main.root_health",  # Fly.io health checks
            "dispatch.health",   # dispatch health check
        }
        public_paths = {"/pick_tracker", "/api/smart_scan"}
        public_path_prefixes = (
            "/kiosk/",
            "/tv/",
            "/confirm_picker/",
            "/input_pick/",
            "/complete_pick/",
            "/start_pick/",
        )
        if request.endpoint in public_endpoints:
            return
        # Kiosk, TV, and the legacy pick-tracker flow run on shared floor devices.
        if request.path in public_paths or request.path.startswith(public_path_prefixes):
            return
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.url))

    @app.route("/api/set-branch", methods=["POST"])
    def api_set_branch():
        from flask import jsonify, request, session
        data = request.get_json(silent=True) or {}
        raw = data.get("branch", "")
        branch = normalize_branch(raw)
        session["selected_branch"] = branch or ""
        return jsonify({"ok": True, "branch": branch or "", "label": branch_label(branch)})

    fly_runtime = is_fly_runtime()

    default_run_migrations = True
    run_migrations_on_start = env_bool("RUN_MIGRATIONS_ON_START", default_run_migrations)
    if run_migrations_on_start:
        with app.app_context():
            _run_migrations(app)
    else:
        app.logger.info("Skipping runtime migrations on startup.")

    upload_folder = app.config.get("UPLOAD_FOLDER")
    if upload_folder:
        os.makedirs(upload_folder, exist_ok=True)
        if fly_runtime:
            app.logger.warning(
                "UPLOAD_FOLDER uses local disk storage (%s); files are not durable across Fly machine replacement unless a volume is mounted.",
                upload_folder,
            )

    return app

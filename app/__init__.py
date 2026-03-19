import os

from flask import Flask
from flask_migrate import upgrade
from .extensions import db, migrate
from .Models.models import CreditImage, CustomerNote, ERPDeliveryKPI, ERPMirrorArOpen, ERPMirrorArOpenDetail, ERPMirrorCustomer, ERPMirrorCustomerShipTo, ERPMirrorItem, ERPMirrorItemBranch, ERPMirrorItemUomConv, ERPMirrorPick, ERPMirrorPickDetailNormalized, ERPMirrorPickHeaderNormalized, ERPMirrorPrintTransaction, ERPMirrorPrintTransactionDetail, ERPMirrorSalesOrderHeader, ERPMirrorSalesOrderLine, ERPMirrorShipmentHeader, ERPMirrorShipmentLine, ERPMirrorWorkOrder, ERPMirrorWorkOrderHeader, ERPSyncBatch, ERPSyncState, ERPSyncTableState, Pick, PickAssignment, PickTypes, Pickster, WorkOrder  # noqa: F401
from .Models.central_db import CentralSalesOrder, CentralSalesOrderLine, CentralInventory, CentralCustomer, CentralDispatchOrder # noqa: F401
from .Routes.routes import main as main_blueprint
from .Routes.dispatch_routes import dispatch as dispatch_blueprint
from .Routes.sales_routes import sales as sales_blueprint
from .runtime_settings import env_bool, get_central_db_url, get_database_url, is_pooled_postgres_url


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
    """Run pending Alembic migrations, recovering from branched-state errors."""
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

    if app.config.get("VERCEL") or os.environ.get("VERCEL"):
        primary_url = get_database_url()
        central_url = get_central_db_url()
        if primary_url and not is_pooled_postgres_url(primary_url):
            app.logger.warning("DATABASE_URL does not appear to be a pooled Postgres endpoint; burst traffic may exhaust connections.")
        if central_url and not is_pooled_postgres_url(central_url):
            app.logger.warning("CENTRAL_DB_URL does not appear to be a pooled Postgres endpoint; burst mirror reads may exhaust connections.")

    run_migrations_on_start = env_bool("RUN_MIGRATIONS_ON_START", not os.environ.get("VERCEL"))
    if run_migrations_on_start:
        with app.app_context():
            _run_migrations(app)
    else:
        app.logger.info("Skipping runtime migrations on startup.")

    return app

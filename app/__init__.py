from flask import Flask
from flask_migrate import upgrade, stamp
from .extensions import db, migrate
from .Models.models import Pickster, Pick, PickTypes, WorkOrder, PickAssignment, ERPMirrorPick, ERPMirrorWorkOrder, CreditImage, CustomerNote  # noqa: F401
from .Routes.routes import main as main_blueprint
from .Routes.sales_routes import sales as sales_blueprint
def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    # Initialize other extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # Register Blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(sales_blueprint)

    # Run all pending migrations on startup (handles new columns, tables, etc.)
    with app.app_context():
        try:
            upgrade()
        except Exception as e:
            if 'overlaps' in str(e):
                # DB has stale ancestor revision alongside a newer head in
                # alembic_version (caused by mid-chain migration insertions).
                # Stamp to the latest applied revision so upgrade() can proceed.
                app.logger.warning(f"Overlapping Alembic heads detected, stamping to resolve: {e}")
                stamp('d1e2f3a4b5c6')
                upgrade()
            else:
                app.logger.error(f"Error during db upgrade: {e}")

    return app

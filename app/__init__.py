from flask import Flask
from .extensions import db, migrate
from .Models.models import Pickster, Pick, PickTypes, WorkOrder, PickAssignment, ERPMirrorPick, ERPMirrorWorkOrder, CreditImage, CustomerNote, ERPSyncState  # noqa: F401
from .Models.central_db import CentralSalesOrder, CentralSalesOrderLine, CentralInventory, CentralCustomer, CentralDispatchOrder # noqa: F401
from .Routes.routes import main as main_blueprint
from .Routes.dispatch_routes import dispatch as dispatch_blueprint
from .Routes.sales_routes import sales as sales_blueprint

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

    # Ensure tables exist (needed for serverless/fresh deployments)
    with app.app_context():
        try:
            bind_keys = [None]
            if app.config.get('SQLALCHEMY_BINDS', {}).get('central_db'):
                bind_keys.append('central_db')
            db.create_all(bind_key=bind_keys)
        except Exception as e:
            app.logger.error(f"Error during db.create_all(): {e}")

    return app

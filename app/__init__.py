from flask import Flask
from .extensions import db, migrate
from .Models.models import Pickster, Pick, PickTypes, WorkOrder, PickAssignment, ERPMirrorPick, ERPMirrorWorkOrder  # noqa: F401
from .Routes.routes import main as main_blueprint
def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    # Initialize other extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # Register Blueprints
    app.register_blueprint(main_blueprint)

    # Ensure tables exist (needed for serverless/fresh deployments)
    with app.app_context():
        db.create_all()

    return app

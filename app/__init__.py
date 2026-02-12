from flask import Flask
from .extensions import db, migrate
from .Routes.routes import main as main_blueprint


# Import other extensions and blueprints
def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    # Initialize other extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # Register Blueprints
    app.register_blueprint(main_blueprint)
    return app

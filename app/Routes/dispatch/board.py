from flask import render_template
from app.Routes.dispatch import dispatch_bp


@dispatch_bp.get("/")
def index():
    return render_template("dispatch/index.html")

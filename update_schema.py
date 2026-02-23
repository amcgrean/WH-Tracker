import os
from app import create_app, db
from dotenv import load_dotenv

load_dotenv()
app = create_app()
with app.app_context():
    db.create_all()
    print("Cloud DB Schema Updated (create_all called)")

import os
from sqlalchemy import text
from app import create_app
from app.extensions import db

os.environ['RUN_MIGRATIONS_ON_START'] = 'False'
app = create_app()

statements = [
    "ALTER TABLE pick ADD COLUMN IF NOT EXISTS notes TEXT;",
    "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS notes TEXT;",
    "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS completed_by_id INTEGER;",
    "ALTER TABLE work_orders DROP CONSTRAINT IF EXISTS fk_work_orders_completed_by_id;",
    "ALTER TABLE work_orders ADD CONSTRAINT fk_work_orders_completed_by_id FOREIGN KEY (completed_by_id) REFERENCES pickster (id);"
]

with app.app_context():
    with db.engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                print(f"Executed: {stmt}")
            except Exception as e:
                print(f"Skipped/Failed: {stmt} - {e}")

print("Done applying missing columns.")

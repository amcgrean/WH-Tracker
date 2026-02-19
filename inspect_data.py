import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.getenv('DATABASE_URL')
if url and url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url)

with engine.connect() as conn:
    print("--- ERPMirrorPick Sample ---")
    query = text("SELECT * FROM erp_mirror_picks LIMIT 5")
    rows = conn.execute(query).mappings().all()
    for row in rows:
        print(dict(row))

    print("\n--- ERPMirrorWorkOrder Sample ---")
    query = text("SELECT * FROM erp_mirror_work_orders LIMIT 5")
    rows = conn.execute(query).mappings().all()
    for row in rows:
        print(dict(row))

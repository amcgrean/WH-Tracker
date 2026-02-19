import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.getenv('DATABASE_URL')
if url and url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

if not url:
    print("No DATABASE_URL found")
    exit()

print(f"Connecting to: {url[:30]}...")
engine = create_engine(url)

with engine.connect() as conn:
    res1 = conn.execute(text("SELECT COUNT(*) FROM erp_mirror_picks")).scalar()
    res2 = conn.execute(text("SELECT COUNT(*) FROM erp_mirror_work_orders")).scalar()
    print(f"ERPMirrorPick Count: {res1}")
    print(f"ERPMirrorWorkOrder Count: {res2}")

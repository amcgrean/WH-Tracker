import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("DATABASE_URL not set")
    sys.exit(1)

url = DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url)
so_num = '1421978'

with engine.connect() as conn:
    print(f"--- Inspecting SO {so_num} ---")
    
    # Check Picks
    pick = conn.execute(text("SELECT * FROM erp_mirror_picks WHERE so_number = :so"), {"so": so_num}).fetchone()
    print(f"Pick Record: {pick}")
    if not pick:
        # Check for spaces or other issues
        all_picks = conn.execute(text("SELECT so_number FROM erp_mirror_picks LIMIT 5")).fetchall()
        print(f"Other SOs in Picks: {all_picks}")

    # Check Work Orders
    wos = conn.execute(text("SELECT * FROM erp_mirror_work_orders WHERE so_number = :so"), {"so": so_num}).fetchall()
    print(f"Work Order Count: {len(wos)}")
    if wos:
        print(f"First WO: {wos[0]}")
    else:
        # Check for spaces or other issues
        all_wos = conn.execute(text("SELECT so_number FROM erp_mirror_work_orders LIMIT 5")).fetchall()
        print(f"Other SOs in WOs: {all_wos}")

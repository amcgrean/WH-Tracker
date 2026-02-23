import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(url)

with engine.connect() as conn:
    sql = text("SELECT so_number FROM erp_mirror_picks WHERE so_number LIKE '%1421978%' LIMIT 1")
    r = conn.execute(sql).fetchone()
    if r:
        print(f"REPR: {repr(r[0])}")
        print(f"LEN: {len(r[0])}")
    else:
        print("NOT FOUND")

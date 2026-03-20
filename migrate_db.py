import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import time

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("No DATABASE_URL found.")
    exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("Adding local_pick_state column...")
        try:
            conn.execute(text("ALTER TABLE erp_mirror_picks ADD COLUMN local_pick_state VARCHAR(50);"))
            print("Successfully added local_pick_state.")
        except Exception as e:
            print(f"Error (might exist): {e}")

        print("Adding route column...")
        try:
            conn.execute(text("ALTER TABLE erp_mirror_picks ADD COLUMN route VARCHAR(128);"))
            print("Successfully added route.")
        except Exception as e:
            print(f"Error (might exist): {e}")

        print("Adding GPS columns...")
        columns_to_add = [
            ("latitude", "DOUBLE PRECISION"), # Using double precision for Postgres/SQLite compatibility in scripts
            ("longitude", "DOUBLE PRECISION"),
            ("geocode_status", "VARCHAR(50)")
        ]
        
        for col, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE erp_mirror_picks ADD COLUMN {col} {col_type};"))
                print(f"Successfully added {col}.")
            except Exception as e:
                print(f"Error adding {col} (might exist): {e}")
            
    print("Database schema updated successfully.")
except Exception as e:
    print(f"Connection failed: {e}")

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def update_schema():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if not url:
        print("DATABASE_URL not found")
        return
        
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("Updating schema for erp_mirror_picks and erp_mirror_work_orders...")
        try:
            # erp_mirror_picks columns
            columns_picks = [
                ("system_id", "VARCHAR(50)"),
                ("expect_date", "VARCHAR(50)"),
                ("sale_type", "VARCHAR(50)"),
                ("local_pick_state", "VARCHAR(50)"),
                ("ship_via", "VARCHAR(128)"),
                ("driver", "VARCHAR(128)"),
                ("route", "VARCHAR(128)"),
                ("printed_at", "TIMESTAMP"),
                ("staged_at", "TIMESTAMP"),
                ("delivered_at", "TIMESTAMP"),
                ("latitude", "DOUBLE PRECISION"),
                ("longitude", "DOUBLE PRECISION"),
                ("geocode_status", "VARCHAR(50)")
            ]
            
            for col_name, col_type in columns_picks:
                print(f"Adding {col_name} to erp_mirror_picks...")
                conn.execute(text(f"ALTER TABLE erp_mirror_picks ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            
            # erp_mirror_work_orders columns
            print("Adding so_number to erp_mirror_work_orders...")
            conn.execute(text("ALTER TABLE erp_mirror_work_orders ADD COLUMN IF NOT EXISTS so_number VARCHAR(128)"))
            
            conn.commit()
            print("Successfully updated schema.")
        except Exception as e:
            print(f"Error updating schema: {e}")

if __name__ == "__main__":
    update_schema()

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def verify():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not found")
        return
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            pick_count = conn.execute(text("SELECT COUNT(*) FROM erp_mirror_picks")).scalar()
            gps_count = conn.execute(text("SELECT COUNT(*) FROM erp_mirror_picks WHERE latitude IS NOT NULL")).scalar()
            print(f"Picks synced: {pick_count}")
            print(f"GPS coordinated matched: {gps_count}")
            
            if pick_count > 0:
                print("\nSample Synced Picks (Top 5):")
                result = conn.execute(text("SELECT so_number, customer_name, address, latitude, longitude FROM erp_mirror_picks WHERE latitude IS NOT NULL LIMIT 5"))
                for row in result:
                    print(row)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()

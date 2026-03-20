import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def verify():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not found")
        return
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("Checking tables...")
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"Tables found: {tables}")
        
        if 'erp_mirror_picks' in tables:
            cur.execute("SELECT COUNT(*) FROM erp_mirror_picks")
            count = cur.fetchone()[0]
            print(f"Total Picks: {count}")
            
            cur.execute("SELECT COUNT(*) FROM erp_mirror_picks WHERE latitude IS NOT NULL")
            gps_count = cur.fetchone()[0]
            print(f"GPS Matched: {gps_count}")
            
            if gps_count > 0:
                print("\nRecent GPS matches:")
                cur.execute("SELECT so_number, customer_name, latitude, longitude, geocode_status FROM erp_mirror_picks WHERE latitude IS NOT NULL LIMIT 5")
                for r in cur.fetchall():
                    print(r)
        else:
            print("erp_mirror_picks table NOT FOUND!")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    verify()

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def check_synced_data():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if not url:
        print("Error: DATABASE_URL not found in .env")
        return

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print("Summary of Synced Statuses in Cloud DB:")
            result = conn.execute(text("SELECT so_status, shipment_status, COUNT(*) FROM erp_mirror_picks GROUP BY so_status, shipment_status"))
            rows = result.fetchall()
            if not rows:
                print("No data found in erp_mirror_picks.")
            else:
                print(f"{'SO Status':<10} | {'Ship Status':<12} | {'Count'}")
                print("-" * 35)
                for row in rows:
                    print(f"{str(row[0]):<10} | {str(row[1]):<12} | {row[2]}")
            
            print("\nRecent Picks Sample:")
            result = conn.execute(text("SELECT so_number, customer_name, so_status, shipment_status FROM erp_mirror_picks ORDER BY synced_at DESC LIMIT 10"))
            for row in result:
                print(row)
                
    except Exception as e:
        print(f"Error checking data: {e}")

if __name__ == "__main__":
    check_synced_data()

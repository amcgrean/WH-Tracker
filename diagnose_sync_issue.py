import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import sys

# Add app directory to path
sys.path.append(os.getcwd())

from sync_erp import LocalSync

def diagnose_mapping():
    load_dotenv()
    syncer = LocalSync()
    
    print("Fetching local data...")
    data = syncer.fetch_local_data()
    picks = data.get('picks', [])
    
    if not picks:
        print("No picks found.")
        return

    print(f"Total picks fetched: {len(picks)}")
    
    # Check if any have status
    status_counts = {}
    for p in picks:
        s = p.get('so_status')
        status_counts[s] = status_counts.get(s, 0) + 1
    
    print(f"Local status distribution: {status_counts}")
    
    # Sample mapping
    first_p = picks[0]
    mapping = {
        'so_number': str(first_p.get('so_number')),
        'so_status': first_p.get('so_status'),
        'shipment_status': first_p.get('shipment_status'),
    }
    print(f"Sample mapping for sync: {mapping}")

    # Check Cloud DB timestamps
    url = os.getenv('DATABASE_URL')
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(url)
    with engine.connect() as conn:
        print("\nCloud DB Timestamp Check:")
        result = conn.execute(text("SELECT synced_at, COUNT(*) FROM erp_mirror_picks GROUP BY synced_at ORDER BY synced_at DESC LIMIT 5"))
        for row in result:
            print(f"Synced At: {row[0]}, Count: {row[1]}")

if __name__ == "__main__":
    diagnose_mapping()

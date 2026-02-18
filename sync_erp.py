import requests
import time
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Configuration
API_URL = os.getenv('CLOUD_API_URL', 'http://localhost:5000/erp-cloud-sync')
API_KEY = os.getenv('SYNC_API_KEY', 'dev-key')
DATABASE_URL = os.getenv('DATABASE_URL')
SYNC_INTERVAL = 300  # 5 minutes

class LocalSync:
    def __init__(self):
        from app.Services.erp_service import ERPService
        self.erp = ERPService()
        self.db_session = None
        
        if DATABASE_URL:
            # Handle postgres:// to postgresql:// conversion for SQLAlchemy 1.4+
            url = DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            
            print(f"[{datetime.now()}] Direct SQL Mode Enabled. Connecting to Cloud DB...")
            try:
                self.engine = create_engine(url)
                self.Session = sessionmaker(bind=self.engine)
                self.db_session = self.Session()
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                print(f"[{datetime.now()}] Cloud DB Connection Successful.")
            except Exception as e:
                print(f"[{datetime.now()}] Cloud DB Connection Failed: {e}")
                self.db_session = None

    def fetch_local_data(self):
        print(f"[{datetime.now()}] Fetching data from local ERP...")
        try:
            # Fetch Picks
            picks = self.erp.get_open_so_summary()
            
            # Fetch Work Orders
            work_orders = self.erp.get_open_work_orders()
            
            return {
                'picks': picks,
                'work_orders': work_orders
            }
        except Exception as e:
            print(f"Error fetching local data: {e}")
            return None

    def push_to_cloud(self, data):
        """Pushes data to cloud using either Direct SQL or API fallback."""
        if self.db_session:
            self.push_direct_to_db(data)
        else:
            self.push_via_api(data)

    def push_direct_to_db(self, data):
        """High-performance direct push to cloud database."""
        from app.Models.models import ERPMirrorPick, ERPMirrorWorkOrder
        
        try:
            print(f"[{datetime.now()}] Starting Direct SQL Push...")
            
            # 1. Sync Picks
            picks_data = data.get('picks', [])
            if picks_data:
                print(f"[{datetime.now()}] Clearing and updating {len(picks_data)} Picks...")
                self.db_session.query(ERPMirrorPick).delete()
                
                # Bulk mapping for speed
                mappings = [
                    {
                        'so_number': str(p.get('so_number')),
                        'customer_name': p.get('customer_name'),
                        'address': p.get('address'),
                        'reference': p.get('reference'),
                        'handling_code': p.get('handling_code'),
                        'line_count': int(p.get('line_count', 0)),
                        'synced_at': datetime.utcnow()
                    } for p in picks_data
                ]
                self.db_session.bulk_insert_mappings(ERPMirrorPick, mappings)

            # 2. Sync Work Orders
            wos_data = data.get('work_orders', [])
            if wos_data:
                print(f"[{datetime.now()}] Clearing and updating {len(wos_data)} Work Orders...")
                self.db_session.query(ERPMirrorWorkOrder).delete()
                
                # Bulk mapping for large dataset speed (60k items)
                # We process in chunks even for direct SQL to manage memory/transaction size
                chunk_size = 5000
                for i in range(0, len(wos_data), chunk_size):
                    chunk = wos_data[i:i + chunk_size]
                    mappings = [
                        {
                            'wo_id': str(wo.get('wo_id')),
                            'so_number': str(wo.get('so_number')),
                            'description': wo.get('description'),
                            'item_number': wo.get('item_number'),
                            'status': wo.get('status'),
                            'qty': float(wo.get('qty', 0)),
                            'department': wo.get('department'),
                            'synced_at': datetime.utcnow()
                        } for wo in chunk
                    ]
                    self.db_session.bulk_insert_mappings(ERPMirrorWorkOrder, mappings)
                    print(f"[{datetime.now()}]   Pushed {min(i + chunk_size, len(wos_data))} / {len(wos_data)} WOs...")

            self.db_session.commit()
            print(f"[{datetime.now()}] Direct SQL Push Completed Successfully.")
            
        except Exception as e:
            self.db_session.rollback()
            print(f"[{datetime.now()}] Direct SQL Push Failed: {e}")
            print("Attempting API Fallback...")
            self.push_via_api(data)

    def push_via_api(self, data):
        """Standard API-based chunked push (Fallback)."""
        chunk_size = 500
        
        picks = data.get('picks', [])
        for i in range(0, len(picks), chunk_size):
            chunk = picks[i:i + chunk_size]
            is_first = (i == 0)
            self._send_payload({'picks': chunk}, reset=is_first)

        wos = data.get('work_orders', [])
        for i in range(0, len(wos), chunk_size):
            chunk = wos[i:i + chunk_size]
            is_first = (i == 0 and not picks) 
            self._send_payload({'work_orders': chunk}, reset=is_first)

    def _send_payload(self, payload, reset=True):
        """Helper to send a single chunk to the API."""
        try:
            headers = {'X-API-KEY': API_KEY}
            params = {'reset': 'true' if reset else 'false'}
            response = requests.post(API_URL, json=payload, headers=headers, params=params, timeout=60)
            
            if response.status_code == 200:
                print(f"[{datetime.now()}] API Chunk Sync Successful.")
            else:
                print(f"[{datetime.now()}] API Chunk Sync Failed: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"Error pushing via API: {e}")

    def run(self):
        print("Starting Local ERP Sync Service (v2.0 Direct SQL Support)...")
        while True:
            data = self.fetch_local_data()
            if data:
                self.push_to_cloud(data)
            
            print(f"Sleeping for {SYNC_INTERVAL} seconds...")
            time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    try:
        syncer = LocalSync()
        syncer.run()
    except KeyboardInterrupt:
        print("\nStopping Sync Service.")
    except Exception as e:
        print(f"Fatal Error: {e}")

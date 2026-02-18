import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_URL = os.getenv('CLOUD_API_URL', 'http://localhost:5000/api/sync')  # Update with production URL
API_KEY = os.getenv('SYNC_API_KEY', 'dev-key')
SYNC_INTERVAL = 300  # 5 minutes

class LocalSync:
    def __init__(self):
        from app.Services.erp_service import ERPService
        self.erp = ERPService()

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
        """Pushes data to cloud in chunks to avoid payload size limits."""
        chunk_size = 500
        
        # 1. Push Picks
        picks = data.get('picks', [])
        for i in range(0, len(picks), chunk_size):
            chunk = picks[i:i + chunk_size]
            is_first = (i == 0)
            print(f"[{datetime.now()}] Pushing Picks chunk {i//chunk_size + 1} ({len(chunk)} items)...")
            self._send_payload({'picks': chunk}, reset=is_first)

        # 2. Push Work Orders
        wos = data.get('work_orders', [])
        for i in range(0, len(wos), chunk_size):
            chunk = wos[i:i + chunk_size]
            # Reset only on the absolute first push of the whole cycle
            # (If we already pushed picks, we should append WOs)
            is_first = (i == 0 and not picks) 
            print(f"[{datetime.now()}] Pushing WOs chunk {i//chunk_size + 1} ({len(chunk)} items)...")
            self._send_payload({'work_orders': chunk}, reset=is_first)

    def _send_payload(self, payload, reset=True):
        """Helper to send a single chunk to the API."""
        try:
            headers = {'X-API-KEY': API_KEY}
            params = {'reset': 'true' if reset else 'false'}
            response = requests.post(API_URL, json=payload, headers=headers, params=params)
            
            if response.status_code == 200:
                print("Chunk sync successful!")
            else:
                print(f"Chunk sync failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error pushing chunk: {e}")

    def run(self):
        print("Starting Local ERP Sync Service...")
        while True:
            data = self.fetch_local_data()
            if data:
                self.push_to_cloud(data)
            
            print(f"Sleeping for {SYNC_INTERVAL} seconds...")
            time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    # We need to setup the Flask app context just to use the models/extensions if needed,
    # but strictly speaking ERPService might depend on ODBC which doesn't need Flask context 
    # unless it uses current_app config. 
    # Let's assume we can import ERPService directly.
    # However, if ERPService uses 'current_app', we might need to mock it or create a basic app context.
    
    # For simplicity, we'll try running it directly.
    try:
        syncer = LocalSync()
        syncer.run()
    except KeyboardInterrupt:
        print("\nStopping Sync Service.")
    except Exception as e:
        print(f"Fatal Error: {e}")

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
        print(f"[{datetime.now()}] Pushing data to cloud ({len(data['picks'])} picks, {len(data['work_orders'])} WOs)...")
        try:
            headers = {'X-API-KEY': API_KEY}
            response = requests.post(API_URL, json=data, headers=headers)
            
            if response.status_code == 200:
                print("Sync successful!")
            else:
                print(f"Sync failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error pushing to cloud: {e}")

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

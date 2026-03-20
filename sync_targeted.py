from sync_erp import LocalSync
import os
from datetime import datetime

class LocalSyncTest(LocalSync):
    def fetch_local_data(self):
        print(f"[{datetime.now()}] Fetching data from local ERP (Picks & WOs ONLY)...")
        try:
            picks = self.erp.get_open_picks()
            work_orders = self.erp.get_open_work_orders()
            return {
                'picks': picks,
                'work_orders': work_orders,
                'kpis': []
            }
        except Exception as e:
            print(f"Error fetching local data: {e}")
            return None

if __name__ == "__main__":
    print("Running Targeted Sync (Picks & WOs only)...")
    syncer = LocalSyncTest()
    data = syncer.fetch_local_data()
    if data:
        syncer.push_to_cloud(data)
        print("Targeted Sync Complete.")

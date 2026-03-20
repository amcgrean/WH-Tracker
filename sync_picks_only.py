from sync_erp import LocalSync
import os
from datetime import datetime

class LocalSyncPicks(LocalSync):
    def fetch_local_data(self):
        print(f"[{datetime.now()}] Fetching PICKS ONLY from local ERP...")
        try:
            picks = self.erp.get_open_picks()
            return {
                'picks': picks,
                'work_orders': [],
                'kpis': []
            }
        except Exception as e:
            print(f"Error fetching local data: {e}")
            return None

if __name__ == "__main__":
    print("Starting Picks-Only Sync for fast verification...")
    syncer = LocalSyncPicks()
    data = syncer.fetch_local_data()
    if data:
        print(f"Fetched {len(data['picks'])} picks. pushing to cloud...")
        syncer.push_to_cloud(data)
        print("Picks-Only Sync Complete.")

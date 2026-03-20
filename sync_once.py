import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sync_erp import LocalSync

if __name__ == "__main__":
    sync = LocalSync()
    data = sync.fetch_local_data()
    if data:
        print("Pushing data to cloud...")
        sync.push_to_cloud(data)
        print("Done.")
    else:
        print("No data fetched.")

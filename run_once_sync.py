from sync_erp import LocalSync
import os
from dotenv import load_dotenv

load_dotenv()
print("Starting One-Off Sync...")
syncer = LocalSync()
data = syncer.fetch_local_data()
if data:
    syncer.push_to_cloud(data)
    print("Sync Completed successfully (including detailed pick lines).")
else:
    print("Failed to fetch local data.")

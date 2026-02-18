import os
import json
import sys
from sync_erp import LocalSync
from dotenv import load_dotenv

load_dotenv()

def test_sync():
    print("--- Starting Sync Test (Size Check) ---")
    syncer = LocalSync()
    
    data = syncer.fetch_local_data()
    
    if data:
        payload = json.dumps(data)
        size_kb = len(payload) / 1024
        print(f"Payload Size: {size_kb:.2f} KB")
        print(f"Total Items: {len(data['picks'])} picks, {len(data['work_orders'])} WOs")
        
        if size_kb > 4000:
            print("WARNING: Payload is approaching Vercel's 4.5MB limit.")
        
        # Test Cloud Push
        syncer.push_to_cloud(data)
    else:
        print("FAILED: Could not fetch data.")

if __name__ == "__main__":
    test_sync()

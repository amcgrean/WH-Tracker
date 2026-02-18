import os
import requests
from dotenv import load_dotenv

load_dotenv()

def diagnostic():
    sync_url = os.getenv('CLOUD_API_URL')
    if not sync_url:
        print("ERROR: CLOUD_API_URL not found in .env")
        return

    base_url = sync_url.split('/erp-cloud-sync')[0]
    print(f"Testing Base URL: {base_url}")
    
    # 1. Test GET root
    try:
        r = requests.get(base_url, timeout=10)
        print(f"GET /: Status {r.status_code}")
        print(f"Content Sample: {r.text[:200]}")
    except Exception as e:
        print(f"GET /: FAILED - {e}")

    # 2. Test POST to the sync route
    print(f"\nTesting Sync URL: {sync_url}")
    try:
        api_key = os.getenv('SYNC_API_KEY')
        r = requests.post(sync_url, json={}, headers={'X-API-KEY': api_key}, timeout=10)
        print(f"POST {sync_url}: Status {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"POST {sync_url}: FAILED - {e}")

if __name__ == "__main__":
    diagnostic()

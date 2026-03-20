import os
import requests
from dotenv import load_dotenv

load_dotenv()

def diagnostic():
    base_url = os.getenv('TRACKER_BASE_URL')
    if not base_url:
        print("ERROR: TRACKER_BASE_URL not found in .env")
        return

    print(f"Testing Base URL: {base_url}")
    
    # 1. Test GET root
    try:
        r = requests.get(base_url, timeout=10)
        print(f"GET /: Status {r.status_code}")
        print(f"Content Sample: {r.text[:200]}")
    except Exception as e:
        print(f"GET /: FAILED - {e}")

    # 2. Test sync health endpoint
    status_url = f"{base_url.rstrip('/')}/api/sync/status"
    print(f"\nTesting Sync Status URL: {status_url}")
    try:
        r = requests.get(status_url, timeout=10)
        print(f"GET {status_url}: Status {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"GET {status_url}: FAILED - {e}")

if __name__ == "__main__":
    diagnostic()

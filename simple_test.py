import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test():
    base_url = os.getenv('TRACKER_BASE_URL', 'https://wh-tracker-omega.vercel.app')
    status_url = f"{base_url.rstrip('/')}/api/sync/status"
    print(f"GET {status_url}")
    
    try:
        r = requests.get(status_url, timeout=15)
        print(f"Status: {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()

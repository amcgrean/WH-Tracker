import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test():
    sync_url = "https://wh-tracker-omega.vercel.app/erp-cloud-sync"
    api_key = os.getenv('SYNC_API_KEY')
    print(f"POST {sync_url}")
    print(f"Using Key: {api_key}")
    
    try:
        # Send a tiny valid payload
        payload = {"picks": [], "work_orders": []}
        r = requests.post(sync_url, json=payload, headers={'X-API-KEY': api_key}, timeout=15)
        print(f"Status: {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()

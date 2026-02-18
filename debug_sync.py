import requests

def debug_405():
    url = "https://wh-tracker-omega.vercel.app/api/sync"
    print(f"GET {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Status: {r.status_code}")
        print(f"Headers: {dict(r.headers)}")
        print(f"Response (starts with): {r.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_405()

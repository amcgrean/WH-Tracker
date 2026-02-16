import os
import requests

def test_samsara():
    api_token = os.environ.get('SAMSARA_API_TOKEN')
    if not api_token:
        print("SAMSARA_API_TOKEN not found in environment.")
        return

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    # List tags
    url = 'https://api.samsara.com/tags'
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        print("Tags found:")
        for tag in data.get('data', []):
            print(f"ID: {tag.get('id')}, Name: {tag.get('name')}")
    except Exception as e:
        print(f"Error fetching tags: {e}")

if __name__ == "__main__":
    test_samsara()

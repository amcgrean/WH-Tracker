import os
import requests
from dotenv import load_dotenv

def test_samsara():
    load_dotenv()
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

    # Test Locations
    url = 'https://api.samsara.com/fleet/vehicles/locations'
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        locations = data.get('data', [])
        print(f"\nLocations found ({len(locations)}):")
        for loc in locations[:5]: # Show first 5
            v_loc = loc.get('location', {})
            print(f"Vehicle: {loc.get('name')}, Lat: {v_loc.get('latitude')}, Lng: {v_loc.get('longitude')}, Speed: {v_loc.get('speedMilesPerHour')}")
    except Exception as e:
        print(f"Error fetching locations: {e}")

if __name__ == "__main__":
    test_samsara()

from dotenv import load_dotenv
load_dotenv()
from app.Services.samsara_service import SamsaraService
import json

s = SamsaraService()
print("Using Token:", s.api_token[:5] if s.api_token else "NO TOKEN")
data = s._get('/fleet/vehicles/locations')
if data and 'data' in data and len(data['data']) > 0:
    print(json.dumps(data['data'][0], indent=2))
else:
    print("No data or using mock")

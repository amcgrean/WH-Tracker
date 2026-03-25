import os
import sys

# Add the app directory to the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.Services.erp_service import ERPService
from app.Services.samsara_service import SamsaraService
from app import create_app
import json

app = create_app()

with app.app_context():
    erp = ERPService()
    s_srv = SamsaraService()
    
    print("\n--- Testing Sales Delivery Tracker (Route included) ---")
    deliveries = erp.get_sales_delivery_tracker()
    for d in deliveries[:5]:
        print(f"SO: {d['so_number']}, Label: {d['status_label']}, Route: {d.get('route')}")
        
    print("\n--- Testing Samsara Service ---")
    locs = s_srv.get_vehicle_locations()
    for l in locs[:3]:
        print(f"Vehicle: {l['name']}, Speed: {l['speed_mph']} mph, Address: {l['address']}")

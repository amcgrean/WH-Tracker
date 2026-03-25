import os
import sys
from datetime import datetime

# Add the app directory to the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.Services.erp_service import ERPService
from app import create_app

app = create_app()

with app.app_context():
    erp = ERPService()
    
    print("\n--- Testing Open SO Summary ---")
    summary = erp.get_open_so_summary()
    for s in summary[:5]:
        print(f"SO: {s['so_number']}, State: {s.get('local_pick_state')}, Lines: {s['line_count']}")
        
    print("\n--- Testing Sales Delivery Tracker ---")
    deliveries = erp.get_sales_delivery_tracker()
    for d in deliveries[:5]:
        print(f"SO: {d['so_number']}, Label: {d['status_label']}, State: {d.get('local_pick_state')}")

import os
import sys

# Add the app directory to the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.Services.erp_service import ERPService
from datetime import datetime

def debug_counts():
    erp = ERPService()
    
    # 1. Fetch tracker data for 20gr
    deliveries = erp.get_sales_delivery_tracker(branch_id='20gr')
    
    print(f"Total Deliveries Returned for 20GR: {len(deliveries)}")
    
    # 2. Replicate UI grouping logic
    groups = {
        'transit': 0,
        'staged': 0,
        'picking': 0,
        'open': 0
    }
    
    counts_by_label = {}
    
    for d in deliveries:
        # Template logic:
        # {% set label = d.status_label|upper %}
        label = str(d.get('status_label', '')).upper()
        
        # Track raw labels
        counts_by_label[label] = counts_by_label.get(label, 0) + 1
        
        target_group = 'open'
        
        if label == 'INVOICED' or 'EN ROUTE' in label or 'DELIVERED' in label:
            target_group = 'transit'
        elif 'STAGED' in label or 'LOADED' in label:
            target_group = 'staged'
        elif label == 'PICKING':
            target_group = 'picking'
            
        groups[target_group] += 1
        
    print("\n--- Summary by UI Group ---")
    print(f"En Route / Delivered (transit): {groups['transit']}")
    print(f"Staged / Loaded (staged):       {groups['staged']}")
    print(f"Picking / In Progress (picking):{groups['picking']}")
    print(f"Awaiting Action (open):         {groups['open']}")
    
    print("\n--- Summary by Status Label ---")
    for label, count in sorted(counts_by_label.items()):
        print(f"{label}: {count}")

if __name__ == "__main__":
    # Ensure local mode for testing
    os.environ['CLOUD_MODE'] = 'false'
    debug_counts()

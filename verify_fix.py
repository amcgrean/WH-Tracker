from app.Services.erp_service import ERPService
from datetime import datetime

def verify_fix():
    erp = ERPService()
    print("Verifying Sales Delivery Tracker fix...")
    
    # We'll use a branch ID if one exists, otherwise just fetch all
    results = erp.get_sales_delivery_tracker()
    
    print(f"Fetched {len(results)} total orders.")
    
    # Check for orders with specific status flags we saw in research ('L', 'D', 'S', 'I')
    with_shipment_status = [r for r in results if r['shipment_status'] and r['shipment_status'] != '']
    
    print(f"Orders with non-blank shipment status: {len(with_shipment_status)}")
    
    for r in with_shipment_status[:10]:
        print(f"SO: {r['so_number']}, Status: {repr(r['shipment_status'])}, Label: {r['status_label']}, Cust: {r['customer_name']}")

    # Check mapping logic
    staged_loaded = [r for r in results if r['status_label'] == 'STAGED - LOADED']
    print(f"Orders labeled 'STAGED - LOADED': {len(staged_loaded)}")
    
    invoiced = [r for r in results if r['status_label'] == 'INVOICED']
    print(f"Orders labeled 'INVOICED': {len(invoiced)}")

if __name__ == "__main__":
    verify_fix()

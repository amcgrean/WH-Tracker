from app.Services.erp_service import ERPService
from collections import Counter

def check_for_duplicates():
    erp = ERPService()
    # Mock cloud mode to false for local testing if needed, but erp_service handles it
    deliveries = erp.get_sales_delivery_tracker()
    
    so_ids = [d['so_number'] for d in deliveries]
    counts = Counter(so_ids)
    
    duplicates = {so: count for so, count in counts.items() if count > 1}
    
    print(f"Total Deliveries Returned: {len(deliveries)}")
    print(f"Unique SO IDs: {len(counts)}")
    
    if duplicates:
        print("\nDUPLICATES FOUND:")
        for so, count in list(duplicates.items())[:10]:
            print(f"SO {so}: {count} occurrences")
            # Print status info for one of them
            matching = [d for d in deliveries if d['so_number'] == so]
            print(f"  Example Status: {matching[0]['so_status']}, Label: {matching[0]['status_label']}")
    else:
        print("\nNo duplicate SO IDs found in result list.")

    print("\nStatus Distribution:")
    statuses = [d['status_label'] for d in deliveries]
    status_counts = Counter(statuses)
    for stat, count in status_counts.items():
        print(f"  {stat}: {count}")

    print("\nRaw so_status Distribution (first 20):")
    raw_stats = [d['so_status'] for d in deliveries]
    raw_counts = Counter(raw_stats)
    for stat, count in raw_counts.items():
        print(f"  '{stat}': {count}")

if __name__ == "__main__":
    check_for_duplicates()

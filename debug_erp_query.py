from app.Services.erp_service import ERPService

def debug_query():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        # Test 1: Simpler query to see if columns exist
        print("Testing basic so_header columns...")
        test_query = "SELECT TOP 1 so_id, cust_name FROM so_header"
        try:
            cursor.execute(test_query)
            row = cursor.fetchone()
            print(f"Success! Row: {row}")
        except Exception as e:
            print(f"Failed basic query: {e}")

        # Test 2: Full query
        print("\nTesting full summary query...")
        summary = erp.get_open_so_summary()
        print(f"Summary results count: {len(summary)}")
        if summary:
            print(f"First item: {summary[0]}")
        
        conn.close()
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    debug_query()

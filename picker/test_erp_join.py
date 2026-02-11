from app.Services.erp_service import ERPService

def test_joined_query():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        print("Testing JOIN between so_header and cust...")
        query = """
            SELECT TOP 5
                soh.so_id,
                c.cust_name,
                c.address_1,
                c.city
            FROM so_header soh
            JOIN cust c ON soh.cust_key = c.cust_key AND soh.system_id = c.system_id
            WHERE soh.so_status = 'k'
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_joined_query()

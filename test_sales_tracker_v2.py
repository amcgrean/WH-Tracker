import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def query_sales_tracker():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        today = "2026-02-23" # Today's date for consistent testing
        
        print(f"Querying unique SOs for today ({today}) with statuses:")
        # Group by SO fields to avoid duplicates from multiple shipments
        # Use MAX on statuses to get the "furthest along" status if multiple exist
        query = f"""
            SELECT 
                soh.so_id,
                MAX(c.cust_name) as cust_name,
                MAX(cs.address_1) as address_1,
                MAX(cs.city) as city,
                MAX(soh.reference) as reference,
                MAX(soh.so_status) as so_status,
                MAX(sh.status_flag_delivery) as shipment_status,
                COUNT(*) as row_count
            FROM so_header soh
            LEFT JOIN cust c ON soh.cust_key = c.cust_key
            JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id
            WHERE (soh.expect_date = '{today}' OR sh.ship_date = '{today}')
               OR (soh.so_status IN ('k', 'p', 's'))
            GROUP BY soh.so_id
            ORDER BY soh.so_id DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'SO ID':<10} | {'Cust':<15} | {'SO Stat':<8} | {'Ship Stat':<10} | {'Rows'}")
        print("-" * 60)
        for row in rows[:20]:
            print(f"{str(row.so_id):<10} | {str(row.cust_name)[:15]:<15} | {str(row.so_status):<8} | {str(row.shipment_status):<10} | {row.row_count}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    query_sales_tracker()

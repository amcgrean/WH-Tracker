import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def query_sales_tracker_v4():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        print(f"SALES TRACKER QUERY V4 - Today: {today}")
        
        # Logic: 
        # 1. No 'C' (Cancelled)
        # 2. 'I' (Invoiced) only if invoice_date is today
        # 3. K, P, S always included if they are open/active
        # 4. Also include if scheduled/shipped today
        
        query = f"""
            SELECT 
                soh.so_id,
                MAX(c.cust_name) as cust_name,
                MAX(soh.so_status) as so_status,
                MAX(sh.status_flag_delivery) as ship_delv,
                MAX(sh.invoice_date) as invoice_date,
                CASE 
                    WHEN MAX(soh.so_status) = 'K' THEN 'PICKING'
                    WHEN MAX(soh.so_status) = 'P' THEN 'PICKED'
                    WHEN MAX(soh.so_status) = 'S' THEN 
                        CASE 
                            WHEN MAX(sh.status_flag_delivery) = 'E' THEN 'STAGED - EN ROUTE'
                            WHEN MAX(sh.status_flag_delivery) = 'L' THEN 'STAGED - LOADED'
                            WHEN MAX(sh.status_flag_delivery) = 'D' THEN 'STAGED - DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN MAX(soh.so_status) = 'I' THEN 'INVOICED'
                    ELSE MAX(soh.so_status)
                END as status_label
            FROM so_header soh
            LEFT JOIN cust c ON soh.cust_key = c.cust_key
            JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id
            WHERE soh.so_status != 'C'
              AND (
                (soh.so_status IN ('K', 'P', 'S'))
                OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
                OR (soh.expect_date = '{today}' AND soh.so_status != 'I')
                OR (sh.ship_date = '{today}' AND soh.so_status != 'I')
              )
            GROUP BY soh.so_id
            ORDER BY soh.so_id DESC
        """
        
        print("\nSQL Query:")
        print(query)
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"\n{'SO ID':<10} | {'SO Stat':<8} | {'Invoice Date':<12} | {'Status Label'}")
        print("-" * 60)
        for row in rows[:50]:
            print(f"{str(row.so_id):<10} | {str(row.so_status):<8} | {str(row.invoice_date)[:10]:<12} | {row.status_label}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    query_sales_tracker_v4()

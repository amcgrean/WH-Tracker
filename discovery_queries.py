import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def run_query(query, description, out_file):
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        out_file.write(f"\n{'='*70}\n")
        out_file.write(f"--- {description} ---\n")
        
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        out_file.write(" | ".join(columns) + "\n")
        out_file.write("-" * 70 + "\n")
        
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                out_file.write(" | ".join([str(item) for item in row]) + "\n")
        else:
            out_file.write("No data found.\n")
            
        out_file.write(f"{'='*70}\n\n")
        conn.close()
    except Exception as e:
        out_file.write(f"Error querying {description}: {e}\n")

if __name__ == "__main__":
    with open("discovery_output_utf8.txt", "w", encoding="utf-8") as out:
        # 1. Load Timeframe Discovery
        run_query(
            "SELECT TOP 10 cust_name, address_1, start_load_hours, end_load_hours FROM cust_shipto WHERE start_load_hours IS NOT NULL",
            "Load Timeframe: cust_shipto", out
        )
        
        run_query(
            "SELECT TOP 10 shipto_name, shipping_tracking_delv_instruct FROM cust_shipto WHERE shipping_tracking_delv_instruct IS NOT NULL",
            "Load Timeframe: delivery instructions", out
        )

        # 2. Audit History Discovery
        run_query(
            "SELECT TOP 20 system_id, so_id, created_date, created_time, update_date, update_time FROM so_header ORDER BY created_date DESC, created_time DESC",
            "Audit History: so_header dates", out
        )

        run_query(
            "SELECT TOP 5 * FROM pick_header ORDER BY created_date DESC",
            "Audit History: pick_header columns", out
        )
        
        run_query(
            "SELECT TOP 5 * FROM shipments_header ORDER BY created_date DESC",
            "Audit History: shipments_header tracking", out
        )

        # 3. Branch Tag Discovery
        run_query(
            """SELECT TOP 10 soh.so_id, c.cust_name, ib.handling_code, ib.branch 
               FROM so_detail sod 
               JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
               JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
               WHERE ib.branch IN ('10FD', '40CV', '20GR', '25BW')""",
            "Branch Tag: item_branch", out
        )

        # 4. En Route / Driver Match Discovery
        run_query(
            "SELECT TOP 15 so_id, ship_via, driver FROM so_header WHERE driver IS NOT NULL OR ship_via IS NOT NULL ORDER BY created_date DESC",
            "En Route Match: so_header ship_via and driver", out
        )
        
        run_query(
            "SELECT TOP 10 shipment_num, tracking_number, ship_to_address_guid, orig_source_login FROM ship_to_address",
            "En Route Match: ship_to_address", out
        )
        
        run_query(
            "SELECT TOP 5 dispatch_tran_id, type FROM dispatch_tran",
            "En Route Match: dispatch tracking", out
        )

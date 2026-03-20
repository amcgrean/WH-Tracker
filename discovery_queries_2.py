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
    with open("discovery_output_utf8_2.txt", "w", encoding="utf-8") as out:
        # Load Timeframe
        run_query(
            "SELECT TOP 10 shipto_name, address_1, start_load_hours, end_load_hours FROM cust_shipto WHERE start_load_hours IS NOT NULL OR end_load_hours IS NOT NULL",
            "Load Timeframe: start_load_hours and end_load_hours", out
        )

        run_query(
            "SELECT TOP 10 so_id, load_timeframe FROM so_header WHERE load_timeframe IS NOT NULL",
            "Load Timeframe: so_header.load_timeframe", out
        )

        # Audit History
        run_query(
            "SELECT TOP 10 pick_id, so_id, status, created_date, update_date FROM pick_detail ORDER BY created_date DESC",
            "Audit History: pick_detail statuses", out
        )
        
        run_query(
            "SELECT TOP 10 so_id, before_status_870, after_status_870, created_date, created_time FROM so_change_history ORDER BY created_date DESC",
            "Audit History: so_change_history", out
        )
        
        # Branch Tag
        run_query(
            "SELECT TOP 10 so_id, system_id, oe_branch FROM so_header",
            "Branch Tag: system_id from so_header", out
        )

        # En Route Driver/Truck Match
        run_query(
            "SELECT TOP 10 shipment_num, driver, truck, ship_via FROM shipments_header WHERE driver IS NOT NULL OR truck IS NOT NULL ORDER BY created_date DESC",
            "En Route Match: shipments_header driver/truck", out
        )
        
        run_query(
            "SELECT TOP 10 shipment_num, status_flag, status_flag_delivery, loaded_time, ship_date FROM shipments_header WHERE status_flag IN ('L', 'S', 'D') ORDER BY created_date DESC",
            "Shipment Stages: loaded, shipped, delivered", out
        )

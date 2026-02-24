import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

def diagnostic_sales_tracker():
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
        
        print(f"SALES TRACKER DIAGNOSTIC - Today: {today}")
        
        query = f"""
            SELECT 
                soh.so_id,
                MAX(c.cust_name) as cust_name,
                MAX(soh.so_status) as so_status,
                MAX(sh.status_flag_delivery) as shipment_status,
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
                END as status_label,
                COUNT(*) as internal_row_count
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
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        so_ids = [str(row.so_id) for row in rows]
        counts = Counter(so_ids)
        duplicates = {so: count for so, count in counts.items() if count > 1}
        
        print(f"Total Rows in Result: {len(rows)}")
        print(f"Unique SOs: {len(counts)}")
        
        if duplicates:
            print("\n!!! DUPLICATES DETECTED IN SQL RESULT !!!")
            for so, count in list(duplicates.items())[:10]:
                print(f"SO {so}: {count} occurrences")
        else:
            print("\nNo duplicates in SQL result (One row per SO ID).")

        print("\nStatus Distribution:")
        labels = [row.status_label for row in rows]
        label_counts = Counter(labels)
        for label, count in label_counts.items():
            print(f"  {label}: {count}")

        print("\nSample Data (First 20):")
        for row in rows[:20]:
            print(f"SO {row.so_id} | Status: {row.so_status} | Label: {row.status_label} | Internal Join Count: {row.internal_row_count}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnostic_sales_tracker()

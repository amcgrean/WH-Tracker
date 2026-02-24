import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def diagnostic_query():
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
        
        print(f"DIAGNOSTIC QUERY - Today: {today}")
        
        query = f"""
            SELECT TOP 50
                soh.so_id,
                soh.so_status,
                sh.status_flag_delivery,
                sh.status_flag,
                sh.pick_status,
                sh.ship_date,
                soh.expect_date
            FROM so_header soh
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id
            WHERE (soh.expect_date = '{today}' OR sh.ship_date = '{today}')
               OR (soh.so_status IN ('K', 'P', 'S'))
            ORDER BY soh.so_id DESC
        """
        
        print("\nSQL Query:")
        print(query)
        print("\nResults:")
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        header = f"{'SO ID':<10} | {'SO Stat':<8} | {'Ship Fl Del':<12} | {'Ship Fl':<8} | {'Pick Stat':<10} | {'Expect Date'}"
        print(header)
        print("-" * len(header))
        
        for row in rows:
            print(f"{str(row.so_id):<10} | {str(row.so_status):<8} | {str(row.status_flag_delivery):<12} | {str(row.status_flag):<8} | {str(row.pick_status):<10} | {str(row.expect_date)[:10]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnostic_query()

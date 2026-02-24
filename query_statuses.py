import os
import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def query_sample_data():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        today = "2026-02-23" # Hardcoded today based on context for analysis
        
        print(f"Querying orders scheduled for today ({today}):")
        query = f"""
            SELECT TOP 50
                soh.so_id,
                soh.so_status,
                soh.expect_date,
                soh.exp_ship_date,
                sh.pick_status,
                sh.ship_date
            FROM so_header soh
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id
            WHERE (soh.expect_date = '{today}' OR soh.exp_ship_date = '{today}' OR sh.ship_date = '{today}')
            ORDER BY soh.so_id DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'SO ID':<10} | {'Stat':<4} | {'Expect':<10} | {'Exp Ship':<10} | {'Pick S':<6} | {'Ship D'}")
        print("-" * 80)
        for row in rows:
            print(f"{str(row.so_id):<10} | {str(row.so_status):<4} | {str(row.expect_date)[:10]:<10} | {str(row.exp_ship_date)[:10]:<10} | {str(row.pick_status):<6} | {str(row.ship_date)[:10]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    query_sample_data()

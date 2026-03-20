import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

def find_load_fields():
    conn_str = os.getenv('ERP_CONN_STR')
    if not conn_str:
        print("Missing ERP_CONN_STR")
        return

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    tables = ['so_header', 'shipments_header', 'pick_header']
    
    for table in tables:
        print(f"\nScanning table: {table}")
        try:
            for column in cursor.columns(table=table):
                col_name = column.column_name.lower()
                if 'load' in col_name or 'time' in col_name or 'frame' in col_name:
                    print(f"  - Found potential match: {column.column_name}")
        except Exception as e:
            print(f"Error scanning {table}: {e}")
            
    conn.close()

if __name__ == "__main__":
    find_load_fields()

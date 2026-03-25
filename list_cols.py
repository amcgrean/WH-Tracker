import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

def list_cols():
    # Use the same logic as ERPService
    driver = '{SQL Server}'
    server = 'ag01'
    database = 'agility'
    username = 'sa'
    password = 'password' # Fallback
    
    # Try to parse from ERP_CONN_STR if possible
    conn_str = os.getenv('ERP_CONN_STR')
    if conn_str:
        conn = pyodbc.connect(conn_str)
    else:
        connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
        conn = pyodbc.connect(connection_string)
        
    cursor = conn.cursor()
    print("Columns for shipments_header:")
    for column in cursor.columns(table='shipments_header'):
        print(f"  {column.column_name}")
    conn.close()

if __name__ == "__main__":
    list_cols()

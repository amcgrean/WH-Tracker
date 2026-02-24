import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def list_columns(table_name):
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        print(f"Listing columns for {table_name}:")
        cursor.execute(f"SELECT TOP 0 * FROM {table_name}")
        columns = [column[0] for column in cursor.description]
        for col in sorted(columns):
            print(col)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_columns("shipments_header")
    print("\n" + "="*20 + "\n")
    list_columns("shipments_detail")

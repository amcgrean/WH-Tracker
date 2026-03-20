import os
import sys
import pyodbc

# Connect to DB to check shipments_header columns
server = '10.1.1.17'
database = 'AgilitySQL'
username = 'amcgrean'
password = 'Forgefrog69!'
driver = '{ODBC Driver 17 for SQL Server}'

def test_route_field():
    print("Connecting to Agility...")
    try:
        connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        print("\n--- Testing Route/Driver Fields in shipments_header ---")
        query = f"""
            SELECT TOP 15 
                sh.so_id,
                sh.route_id_sysid,
                sh.route_id_char,
                sh.driver
            FROM shipments_header sh
            WHERE sh.route_id_sysid IS NOT NULL 
               OR sh.route_id_char IS NOT NULL 
               OR sh.driver IS NOT NULL
            ORDER BY sh.invoice_date DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'SO Number':<12} | {'route_id_sysid':<15} | {'route_id_char':<15} | {'driver':<15}")
        print("-" * 65)
        for row in rows:
            print(f"{row.so_id:<12} | {str(row.route_id_sysid):<15} | {str(row.route_id_char):<15} | {str(row.driver):<15}")
            
        print("\nReview the output above. Once you determine which column contains the assigned driver, we can proceed with the implementation plan!")
                
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_route_field()

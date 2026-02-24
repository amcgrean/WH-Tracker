import pyodbc
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def check_recent_shipments():
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
        print(f"Checking shipments for today: {today}")
        
        query = f"""
        SELECT TOP 10 
            so_id, system_id, status_flag, status_flag_delivery, ship_date, invoice_date
        FROM shipments_header
        WHERE ship_date >= '{today}' OR update_date >= '{today}'
        ORDER BY update_date DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"Found {len(rows)} recent shipments.")
        for r in rows:
            print(f"SO: {r[0]}, Sys: {r[1]}, Flag: {repr(r[2])}, DelvFlag: {repr(r[3])}, ShipDate: {r[4]}, InvDate: {r[5]}")

        print("\nChecking for ANY non-empty status_flag_delivery in the last 7 days:")
        query_7d = """
        SELECT TOP 5 so_id, status_flag_delivery, update_date
        FROM shipments_header
        WHERE status_flag_delivery != '' AND status_flag_delivery IS NOT NULL
          AND update_date > DATEADD(day, -7, GETDATE())
        """
        cursor.execute(query_7d)
        rows_7d = cursor.fetchall()
        if rows_7d:
            for r in rows_7d:
                print(r)
        else:
            print("No non-empty status_flag_delivery found in last 7 days.")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_recent_shipments()

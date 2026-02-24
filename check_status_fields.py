import pyodbc
from dotenv import load_dotenv

load_dotenv()

def check_status_fields():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        fields = ['status_flag', 'pick_status', 'print_status', 'review_status', 'billed_flag']
        
        for field in fields:
            print(f"\nDistribution of {field} in shipments_header:")
            cursor.execute(f"SELECT {field}, count(1) FROM shipments_header GROUP BY {field}")
            rows = cursor.fetchall()
            for r in rows:
                print(f"{field}: {repr(r[0])}, Count: {r[1]}")

        print("\nChecking a few records where status_flag_delivery is NOT empty if any:")
        cursor.execute("SELECT TOP 5 so_id, status_flag, status_flag_delivery FROM shipments_header WHERE status_flag_delivery != '' AND status_flag_delivery IS NOT NULL")
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(r)
        else:
            print("No records found with non-empty status_flag_delivery.")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_status_fields()

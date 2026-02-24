import pyodbc
from dotenv import load_dotenv

load_dotenv()

def check_e_status():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        print("Checking for ANY 'E' status in history...")
        cursor.execute("SELECT count(1) FROM shipments_header WHERE status_flag = 'E' OR status_flag_delivery = 'E'")
        count = cursor.fetchone()[0]
        print(f"Total count of 'E' status: {count}")
        
        if count > 0:
            cursor.execute("SELECT TOP 5 so_id, status_flag, status_flag_delivery, update_date FROM shipments_header WHERE status_flag = 'E' OR status_flag_delivery = 'E'")
            for r in cursor.fetchall():
                print(r)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_e_status()

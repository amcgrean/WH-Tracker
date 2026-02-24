import pyodbc
from dotenv import load_dotenv

load_dotenv()

def check_distributions():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        print("Distribution of status_flag_delivery in shipments_header:")
        cursor.execute("SELECT status_flag_delivery, count(1) FROM shipments_header GROUP BY status_flag_delivery")
        rows = cursor.fetchall()
        for r in rows:
            print(f"Status: {repr(r[0])}, Count: {r[1]}")

        print("\nChecking for potential padding issues in system_id:")
        cursor.execute("SELECT DISTINCT system_id, LEN(system_id) as length FROM so_header")
        print("so_header system_id:")
        for r in cursor.fetchall():
            print(f"ID: {repr(r[0])}, Length: {r[1]}")

        cursor.execute("SELECT DISTINCT system_id, LEN(system_id) as length FROM shipments_header")
        print("\nshipments_header system_id:")
        for r in cursor.fetchall():
            print(f"ID: {repr(r[0])}, Length: {r[1]}")

        print("\nChecking if any SOs in so_header don't have a match in shipments_header due to system_id mismatch:")
        query = """
        SELECT TOP 5 soh.so_id, soh.system_id, sh.system_id
        FROM so_header soh
        LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id
        WHERE sh.so_id IS NOT NULL AND soh.system_id != sh.system_id
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        if rows:
            print("Found mismatched system_ids for same so_id:")
            for r in rows:
                print(r)
        else:
            print("No system_id mismatches found for joined so_ids.")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_distributions()

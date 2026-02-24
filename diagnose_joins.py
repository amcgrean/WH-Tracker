import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

def diagnose():
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        print("Checking so_header:")
        cursor.execute("SELECT TOP 1 so_id, system_id, cust_key FROM so_header")
        row1 = cursor.fetchone()
        if row1:
            print(f"so_header example: so_id={repr(row1[0])}, system_id={repr(row1[1])}, cust_key={repr(row1[2])}")
            print(f"Types: so_id={type(row1[0])}, system_id={type(row1[1])}, cust_key={type(row1[2])}")
        
        print("\nChecking shipments_header:")
        cursor.execute("SELECT TOP 1 so_id, system_id, status_flag_delivery FROM shipments_header WHERE so_id IS NOT NULL")
        row2 = cursor.fetchone()
        if row2:
            print(f"shipments_header example: so_id={repr(row2[0])}, system_id={repr(row2[1])}, status_flag_delivery={repr(row2[2])}")
            print(f"Types: so_id={type(row2[0])}, system_id={type(row2[1])}, status_flag_delivery={type(row2[2])}")

        print("\nTesting JOIN:")
        query = """
        SELECT TOP 5 soh.so_id, sh.status_flag_delivery
        FROM so_header soh
        JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
        WHERE sh.status_flag_delivery IS NOT NULL
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"Join matches with direct equality: {len(rows)}")
        for r in rows:
            print(r)

        print("\nTesting JOIN with LTRIM/RTRIM:")
        query_trim = """
        SELECT TOP 5 soh.so_id, sh.status_flag_delivery
        FROM so_header soh
        JOIN shipments_header sh ON LTRIM(RTRIM(soh.so_id)) = LTRIM(RTRIM(sh.so_id)) 
            AND LTRIM(RTRIM(soh.system_id)) = LTRIM(RTRIM(sh.system_id))
        WHERE sh.status_flag_delivery IS NOT NULL
        """
        cursor.execute(query_trim)
        rows_trim = cursor.fetchall()
        print(f"Join matches with TRIM: {len(rows_trim)}")
        for r in rows_trim:
            print(r)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()

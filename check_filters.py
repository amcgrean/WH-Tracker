import pyodbc
from datetime import datetime

def check_filters():
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
        print(f"Checking filters for 20GR on {today}...\n")
        
        # 1. Total count of Staged status regardless of Sale Type
        query_staged = """
            SELECT sale_type, count(distinct so_id)
            FROM so_header
            WHERE system_id = '20GR' AND so_status = 'S'
            GROUP BY sale_type
        """
        print("Staged (S) by Sale Type for 20GR:")
        cursor.execute(query_staged)
        for row in cursor.fetchall():
            print(row)

        # 2. Total count of Picking status regardless of Sale Type
        query_picking = """
            SELECT sale_type, count(distinct so_id)
            FROM so_header
            WHERE system_id = '20GR' AND so_status = 'K'
            GROUP BY sale_type
        """
        print("\nPicking (K) by Sale Type for 20GR:")
        cursor.execute(query_picking)
        for row in cursor.fetchall():
            print(row)

        # 3. Check for 'En Route' or 'Invoiced' today
        query_invoiced = """
            SELECT count(distinct so_id)
            FROM so_header
            WHERE system_id = '20GR' AND so_status = 'I' AND update_date = ?
        """
        cursor.execute(query_invoiced, (today,))
        print(f"\nInvoiced (I) for 20GR updated today: {cursor.fetchone()[0]}")

        # 4. Check for 'B' or 'P' (Partial)
        query_partial = """
            SELECT so_status, count(distinct so_id)
            FROM so_header
            WHERE system_id = '20GR' AND so_status IN ('B', 'P')
            GROUP BY so_status
        """
        print("\nPartial (B/P) for 20GR:")
        cursor.execute(query_partial)
        for row in cursor.fetchall():
            print(row)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_filters()

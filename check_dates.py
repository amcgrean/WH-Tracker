import pyodbc
from datetime import datetime

def check_dates():
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
        print(f"Date distribution for 85 Staged orders (20GR) as of {today}:\n")
        
        query = """
            SELECT 
                CASE 
                    WHEN expect_date < ? THEN 'Backlog'
                    WHEN expect_date = ? THEN 'Today'
                    WHEN expect_date > ? THEN 'Future'
                    ELSE 'No Date'
                END as date_group,
                count(*)
            FROM so_header
            WHERE system_id = '20GR' 
              AND so_status = 'S'
              AND sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY 
                CASE 
                    WHEN expect_date < ? THEN 'Backlog'
                    WHEN expect_date = ? THEN 'Today'
                    WHEN expect_date > ? THEN 'Future'
                    ELSE 'No Date'
                END
        """
        cursor.execute(query, (today, today, today, today, today, today))
        for row in cursor.fetchall():
            print(f"{row[0]}: {row[1]}")

        print("\nPicking (K) distribution:")
        cursor.execute(query.replace("so_status = 'S'", "so_status = 'K'"), (today, today, today, today, today, today))
        for row in cursor.fetchall():
            print(f"{row[0]}: {row[1]}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_dates()

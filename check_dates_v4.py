import pyodbc
from datetime import datetime

def check_dates_v4():
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
        print(f"Date distribution for 20GR orders as of {today}:\n")
        
        def run_query(status_list):
            placeholders = ', '.join(['?' for _ in status_list])
            query = f"""
                SELECT date_group, count(distinct so_id) as total
                FROM (
                    SELECT 
                        so_id,
                        CASE 
                            WHEN expect_date < ? THEN 'Backlog'
                            WHEN expect_date = ? THEN 'Today'
                            WHEN expect_date > ? THEN 'Future'
                            ELSE 'No Date'
                        END as date_group
                    FROM so_header
                    WHERE system_id = '20GR' 
                      AND so_status IN ({placeholders})
                      AND sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                ) as sub
                GROUP BY date_group
            """
            params = [today, today, today] + list(status_list)
            cursor.execute(query, params)
            return cursor.fetchall()

        print("--- Staged (S) Distribution ---")
        for row in run_query(['S']):
            print(f"{row[0]}: {row[1]}")

        print("\n--- Picking (K) Distribution ---")
        for row in run_query(['K']):
            print(f"{row[0]}: {row[1]}")

        print("\n--- Partial/B (B, P) Distribution ---")
        for row in run_query(['B', 'P']):
            print(f"{row[0]}: {row[1]}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_dates_v4()

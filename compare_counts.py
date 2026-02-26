import pyodbc
from datetime import datetime

def check_all_branch_counts():
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
        print(f"Comparing All Branches vs 20GR on {today}...\n")
        
        query_template = """
            SELECT 
                CASE 
                    WHEN soh.so_status = 'K' THEN 'PICKING'
                    WHEN soh.so_status = 'P' THEN 'PARTIAL'
                    WHEN soh.so_status = 'B' THEN 'B (PARTIAL)'
                    WHEN soh.so_status = 'S' THEN 
                        CASE 
                            WHEN sh.status_flag = 'E' THEN 'EN ROUTE'
                            WHEN sh.status_flag = 'L' THEN 'LOADED'
                            WHEN sh.status_flag = 'D' THEN 'DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN soh.so_status = 'I' THEN 'INVOICED'
                    ELSE soh.so_status 
                END as status_label,
                COUNT(DISTINCT soh.so_id) as total
            FROM so_header soh
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
            WHERE soh.so_status != 'C'
              {branch_filter}
              AND (
                (soh.expect_date = ?)
                OR (sh.ship_date = ?)
                OR (soh.so_status = 'I' AND sh.invoice_date = ?)
                OR (soh.so_status IN ('K', 'P', 'S', 'B') AND (soh.expect_date <= ?))
              )
              AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY 
                CASE 
                    WHEN soh.so_status = 'K' THEN 'PICKING'
                    WHEN soh.so_status = 'P' THEN 'PARTIAL'
                    WHEN soh.so_status = 'B' THEN 'B (PARTIAL)'
                    WHEN soh.so_status = 'S' THEN 
                        CASE 
                            WHEN sh.status_flag = 'E' THEN 'EN ROUTE'
                            WHEN sh.status_flag = 'L' THEN 'LOADED'
                            WHEN sh.status_flag = 'D' THEN 'DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN soh.so_status = 'I' THEN 'INVOICED'
                    ELSE soh.so_status 
                END
        """
        
        print("--- TOTALS (ALL BRANCHES) ---")
        cursor.execute(query_template.format(branch_filter=""), (today, today, today, today))
        for row in sorted(cursor.fetchall()):
            print(f"{row[0]}: {row[1]}")

        print("\n--- 20GR ONLY ---")
        cursor.execute(query_template.format(branch_filter="AND soh.system_id = '20GR'"), (today, today, today, today))
        for row in sorted(cursor.fetchall()):
            print(f"{row[0]}: {row[1]}")
            
        print("\n--- DISTRIBUTION BY SYSTEM_ID (FOR PICKING) ---")
        cursor.execute("""
            SELECT system_id, count(distinct so_id) 
            FROM so_header 
            WHERE so_status = 'K' 
            AND expect_date <= ?
            AND sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY system_id
        """, (today,))
        for row in cursor.fetchall():
            print(row)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_all_branch_counts()

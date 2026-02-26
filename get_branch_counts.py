import pyodbc
from datetime import datetime

def get_counts(branch_id):
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
        print(f"Counting orders for {branch_id} on {today}...")
        
        query = """
            SELECT 
                CASE 
                    WHEN soh.so_status = 'K' THEN 'PICKING'
                    WHEN soh.so_status = 'P' THEN 'PARTIAL'
                    WHEN soh.so_status = 'S' THEN 
                        CASE 
                            WHEN sh.status_flag = 'E' THEN 'STAGED - EN ROUTE'
                            WHEN sh.status_flag = 'L' THEN 'STAGED - LOADED'
                            WHEN sh.status_flag = 'D' THEN 'STAGED - DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN soh.so_status = 'I' THEN 'INVOICED'
                    ELSE soh.so_status 
                END as status_label,
                COUNT(DISTINCT soh.so_id) as total
            FROM so_header soh
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
            WHERE soh.system_id = ?
              AND soh.so_status != 'C'
              AND (
                (soh.expect_date = ?)
                OR (sh.ship_date = ?)
                OR (soh.so_status = 'I' AND sh.invoice_date = ?)
                OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date <= ?))
              )
              AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY 
                CASE 
                    WHEN soh.so_status = 'K' THEN 'PICKING'
                    WHEN soh.so_status = 'P' THEN 'PARTIAL'
                    WHEN soh.so_status = 'S' THEN 
                        CASE 
                            WHEN sh.status_flag = 'E' THEN 'STAGED - EN ROUTE'
                            WHEN sh.status_flag = 'L' THEN 'STAGED - LOADED'
                            WHEN sh.status_flag = 'D' THEN 'STAGED - DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN soh.so_status = 'I' THEN 'INVOICED'
                    ELSE soh.so_status 
                END
        """
        
        cursor.execute(query, (branch_id, today, today, today, today))
        rows = cursor.fetchall()
        
        counts = {row.status_label: row.total for row in rows}
        
        print("\nSummary for 20GR:")
        for label, count in sorted(counts.items()):
            print(f"{label}: {count}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_counts('20GR')

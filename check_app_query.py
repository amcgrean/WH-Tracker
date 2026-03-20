import pyodbc
from datetime import datetime

def check_app_query():
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
        
        query = f"""
            SELECT 
                MAX(soh.so_status) as so_status,
                MAX(sh.status_flag) as status_flag,
                CASE 
                    WHEN MAX(soh.so_status) = 'K' THEN 'PICKING'
                    WHEN MAX(soh.so_status) = 'B' THEN 'B_PARTIAL'
                    WHEN MAX(soh.so_status) = 'P' THEN 'PARTIAL'
                    WHEN MAX(soh.so_status) = 'S' THEN 
                        CASE 
                            WHEN MAX(sh.status_flag) = 'E' THEN 'STAGED - EN ROUTE'
                            WHEN MAX(sh.status_flag) = 'L' THEN 'STAGED - LOADED'
                            WHEN MAX(sh.status_flag) = 'D' THEN 'STAGED - DELIVERED'
                            ELSE 'STAGED'
                        END
                    WHEN MAX(soh.so_status) = 'I' THEN 'INVOICED'
                    ELSE MAX(soh.so_status)
                END as status_label,
                count(soh.so_id) as cnt
            FROM so_header soh
            LEFT JOIN cust c ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
            LEFT JOIN cust_shipto cs ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
            WHERE soh.so_status != 'C'
              AND soh.system_id = '20GR'
              AND (
                (soh.expect_date = '{today}')
                OR (sh.ship_date = '{today}')
                OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
                OR (soh.so_status IN ('K', 'P', 'B', 'S') AND (soh.expect_date <= '{today}'))
              )
              AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY soh.so_id
        """
        
        print("Executing exact query on 20GR...")
        cursor.execute(query)
        rows = cursor.fetchall()
        
        counts = {}
        target_group_counts = {
            'transit': 0,
            'staged': 0,
            'picking': 0,
            'open': 0
        }

        for r in rows:
            label = str(r.status_label).upper()
            counts[label] = counts.get(label, 0) + 1
            
            target_group = 'open'
            if label == 'INVOICED' or 'EN ROUTE' in label or 'DELIVERED' in label:
                target_group = 'transit'
            elif 'STAGED' in label or 'LOADED' in label:
                target_group = 'staged'
            elif label == 'PICKING':
                target_group = 'picking'
                
            target_group_counts[target_group] += 1
            
        print("\n--- By Status Label ---")
        for k, v in sorted(counts.items()):
            print(f"{k}: {v}")
            
        print("\n--- By target_group in UI ---")
        for k, v in target_group_counts.items():
            print(f"{k}: {v}")
            
    except Exception as e:
        print("Error", e)

if __name__ == "__main__":
    check_app_query()

import pyodbc
from datetime import datetime

def verify_query():
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
        print(f"Testing Sales Delivery Tracker query with status_flag fix for date: {today}")
        
        # This is the same logic now in ERPService.get_sales_delivery_tracker
        query = f"""
            SELECT 
                soh.so_id,
                MAX(c.cust_name) as cust_name,
                MAX(cs.address_1) as address_1,
                MAX(cs.city) as city,
                MAX(soh.reference) as reference,
                MAX(soh.so_status) as so_status,
                MAX(sh.status_flag) as shipment_status,
                MAX(sh.invoice_date) as invoice_date,
                MAX(soh.system_id) as system_id,
                MAX(soh.expect_date) as expect_date,
                CASE 
                    WHEN MAX(soh.so_status) = 'K' THEN 'PICKING'
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
                END as status_label
            FROM so_header soh
            LEFT JOIN cust c ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
            LEFT JOIN cust_shipto cs ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
            LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
            WHERE soh.so_status != 'C'
              AND (
                (soh.expect_date = '{today}')
                OR (sh.ship_date = '{today}')
                OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
                OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date <= '{today}'))
              )
              AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
            GROUP BY soh.so_id
            ORDER BY soh.so_id DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"Fetched {len(rows)} total orders.")
        
        with_status = [r for r in rows if r[6] and r[6] != '']
        print(f"Orders with non-blank shipment status: {len(with_status)}")
        
        for r in with_status[:10]:
            print(f"SO: {r[0]}, Shipment Flag: {repr(r[6])}, Label: {r[10]}, Cust: {r[1]}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_query()

from app.Services.erp_service import ERPService
from datetime import datetime

erp = ERPService()
today = datetime.now().strftime('%Y-%m-%d')

query = f"""
    SELECT 
        COUNT(*)
    FROM so_detail sod
        JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
        JOIN item i ON i.item_ptr = sod.item_ptr
        JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
        LEFT JOIN cust c ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
        LEFT JOIN cust_shipto cs ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
        LEFT JOIN (
            SELECT so_id, system_id, 
                   MAX(status_flag) as status_flag, 
                   MAX(invoice_date) as invoice_date, 
                   MAX(ship_date) as ship_date,
                   MAX(ship_via) as ship_via,
                   MAX(driver) as driver,
                   MAX(route_id_char) as route_id_char,
                   MAX(loaded_time) as loaded_time,
                   MAX(loaded_date) as loaded_date,
                   MAX(status_flag_delivery) as status_flag_delivery
            FROM shipments_header 
            GROUP BY so_id, system_id
        ) sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
        LEFT JOIN (
            SELECT so_id, system_id,
                   MAX(created_date) as created_date,
                   MAX(created_time) as created_time
            FROM pick_header
            WHERE print_status = 'Pick Ticket'
            GROUP BY so_id, system_id
        ) ph ON soh.so_id = ph.so_id AND soh.system_id = ph.system_id
        WHERE soh.so_status != 'C'
          AND (
            (soh.so_status IN ('K', 'P', 'S'))
            OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
            OR (soh.expect_date = '{today}')
            OR (sh.ship_date = '{today}')
          )
          AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
"""

try:
    conn = erp.get_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    count = cursor.fetchone()[0]
    print(f"Total lines returned by query: {count}")
    
    # Check if filters are too aggressive
    print("\nRunning counts for each condition:")
    
    cursor.execute("SELECT COUNT(*) FROM so_header WHERE so_status IN ('K', 'P', 'S')")
    print(f"Status K, P, S: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM so_header WHERE so_status IN ('K', 'P', 'S') AND sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')")
    print(f"Status K, P, S AND NOT Filtered Sale Type: {cursor.fetchone()[0]}")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals(): conn.close()

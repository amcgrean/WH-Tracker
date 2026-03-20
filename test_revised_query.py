from app.Services.erp_service import ERPService
from datetime import datetime

erp = ERPService()
today = datetime.now().strftime('%Y-%m-%d')

# Revised query with correct pick link
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
            SELECT pd.tran_id as so_id, pd.system_id,
                   MAX(ph.created_date) as created_date,
                   MAX(ph.created_time) as created_time
            FROM pick_header ph
            JOIN pick_detail pd ON ph.pick_id = pd.pick_id AND ph.system_id = pd.system_id
            WHERE ph.print_status = 'Pick Ticket' AND pd.tran_type = 'SO'
            GROUP BY pd.tran_id, pd.system_id
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
    print(f"Executing revised query...")
    cursor.execute(query)
    count = cursor.fetchone()[0]
    print(f"Total lines returned: {count}")
    
    if count > 0:
        print("\nFetching first 5 lines:")
        # Select first 5 instead of COUNT(*)
        select_query = query.replace("COUNT(*)", "TOP 5 soh.so_id, sod.sequence, i.item, c.cust_name")
        cursor.execute(select_query)
        for r in cursor.fetchall():
            print(r)
            
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals(): conn.close()

from app.Services.erp_service import ERPService
from datetime import datetime

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

today = datetime.now().strftime('%Y-%m-%d')

query = f"""
    SELECT COUNT(*)
    FROM so_detail sod
    JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
    JOIN item i ON i.item_ptr = sod.item_ptr
    JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
    LEFT JOIN (
        SELECT so_id, system_id, 
               MAX(status_flag) as status_flag, 
               MAX(invoice_date) as invoice_date, 
               MAX(ship_date) as ship_date,
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
    print("Testing FULL query with fixed joins...")
    cursor.execute(query)
    count = cursor.fetchone()[0]
    print(f"Result count: {count}")
    
    if count == 0:
        print("\nChecking ph subquery separately...")
        # Check if pd.tran_id is character and soh.so_id is integer
        cursor.execute("SELECT TOP 1 tran_id FROM pick_detail")
        tid = cursor.fetchone()[0]
        cursor.execute("SELECT TOP 1 so_id FROM so_header")
        sid = cursor.fetchone()[0]
        print(f"Sample tran_id: '{tid}' (type likely {type(tid)})")
        print(f"Sample so_id: {sid} (type likely {type(sid)})")
        
except Exception as e:
    print(f"Error: {e}")

conn.close()

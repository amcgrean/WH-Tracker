from app.Services.erp_service import ERPService
from datetime import datetime

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

today = datetime.now().strftime('%Y-%m-%d')

sections = [
    # 1. Base join
    "SELECT COUNT(*) FROM so_detail sod JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id",
    # 2. Add Status != C
    "SELECT COUNT(*) FROM so_detail sod JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id WHERE soh.so_status != 'C'",
    # 3. Add KPS filter
    "SELECT COUNT(*) FROM so_detail sod JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id WHERE soh.so_status != 'C' AND (soh.so_status IN ('K', 'P', 'S'))",
    # 4. Add sale_type filter
    "SELECT COUNT(*) FROM so_detail sod JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id WHERE soh.so_status != 'C' AND (soh.so_status IN ('K', 'P', 'S')) AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')",
    # 5. Add Item joins
    "SELECT COUNT(*) FROM so_detail sod JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id JOIN item i ON i.item_ptr = sod.item_ptr JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id WHERE soh.so_status IN ('K', 'P', 'S') AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')",
]

for i, q in enumerate(sections, 1):
    try:
        cursor.execute(q)
        count = cursor.fetchone()[0]
        print(f"Step {i}: {count} rows")
    except Exception as e:
        print(f"Step {i} Error: {e}")

conn.close()

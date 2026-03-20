from app.Services.erp_service import ERPService

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

print("--- System ID Comparison for Open Orders ---")
query = """
    SELECT soh.system_id as header_sys, sod.system_id as detail_sys, COUNT(*) 
    FROM so_header soh 
    JOIN so_detail sod ON soh.so_id = sod.so_id 
    WHERE soh.so_status IN ('k', 'p') 
    GROUP BY soh.system_id, sod.system_id
"""
cursor.execute(query)
for r in cursor.fetchall():
    print(f"Header SysID: {r[0]}, Detail SysID: {r[1]} -> Count: {r[2]}")

print("\n--- Checking expect_date and today ---")
from datetime import datetime
today = datetime.now().strftime('%Y-%m-%d')
print(f"Today: {today}")

query = f"""
    SELECT expect_date, COUNT(*) 
    FROM so_header 
    WHERE so_status IN ('k', 'p')
    GROUP BY expect_date
    ORDER BY expect_date DESC
"""
cursor.execute(query)
for r in cursor.fetchall():
    print(f"Expect Date: {r[0]} -> Count: {r[1]}")

conn.close()

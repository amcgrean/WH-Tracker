from app.Services.erp_service import ERPService
from datetime import datetime

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

print(f"Current Time: {datetime.now()}")
today = datetime.now().strftime('%Y-%m-%d')
print(f"Filter Today: {today}")

print("\n--- Testing so_header filters ---")
cursor.execute("SELECT TOP 5 so_id, so_status, sale_type, expect_date, system_id FROM so_header WHERE so_status IN ('K', 'P', 'S')")
rows = cursor.fetchall()
for r in rows:
    print(f"ID: {r.so_id}, Status: {r.so_status}, Type: {r.sale_type}, Expect: {r.expect_date}, System: {r.system_id}")

print("\n--- Testing if any expect_date matches today ---")
cursor.execute(f"SELECT COUNT(*) FROM so_header WHERE expect_date = '{today}'")
print(f"Expect date matches today: {cursor.fetchone()[0]}")

print("\n--- Testing sale_type exclusion ---")
cursor.execute("SELECT DISTINCT sale_type FROM so_header WHERE so_status IN ('K', 'P', 'S')")
types = [r[0] for r in cursor.fetchall()]
print(f"Sale types found for open orders: {types}")

conn.close()

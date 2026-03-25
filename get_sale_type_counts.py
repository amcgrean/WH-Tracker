from app.Services.erp_service import ERPService

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

print("--- Sale Type Counts for Open Orders (K, P, S) ---")
cursor.execute("SELECT sale_type, COUNT(*) FROM so_header WHERE so_status IN ('K', 'P', 'S') GROUP BY sale_type")
for r in cursor.fetchall():
    print(f"{r[0]}: {r[1]}")

print("\n--- Sale Type Counts for ALL In-Process Orders (including 'I') ---")
cursor.execute("SELECT sale_type, COUNT(*) FROM so_header WHERE so_status != 'C' GROUP BY sale_type")
for r in cursor.fetchall():
    print(f"{r[0]}: {r[1]}")

conn.close()

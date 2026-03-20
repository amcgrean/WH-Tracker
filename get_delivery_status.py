from app.Services.erp_service import ERPService

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

print("--- Status Distribution for 'Delivery' Sale Type ---")
cursor.execute("SELECT so_status, COUNT(*) FROM so_header WHERE sale_type = 'Delivery' GROUP BY so_status")
for r in cursor.fetchall():
    print(f"Status {r[0]}: {r[1]}")

print("\n--- Checking if there are any 'K', 'P', or 'S' orders at all ---")
cursor.execute("SELECT so_status, COUNT(*) FROM so_header WHERE so_status IN ('K', 'P', 'S') GROUP BY so_status")
for r in cursor.fetchall():
    print(f"Status {r[0]}: {r[1]}")

conn.close()

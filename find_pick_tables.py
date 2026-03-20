from app.Services.erp_service import ERPService

erp = ERPService()
conn = erp.get_connection()
cursor = conn.cursor()

print("--- Searching for so_id columns in pick% tables ---")
cursor.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE COLUMN_NAME LIKE '%so%' AND TABLE_NAME LIKE 'pick%'")
for r in cursor.fetchall():
    print(f"{r[0]}.{r[1]}")

print("\n--- Searching for pick% tables ---")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'pick%'")
for r in cursor.fetchall():
    print(r[0])
    
conn.close()

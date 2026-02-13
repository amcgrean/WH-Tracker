from app.Services.erp_service import ERPService

def list_tables():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        with open('db_tables.txt', 'w') as f:
            for row in rows:
                f.write(row[0] + '\n')
                
        conn.close()
        print("Done writing to db_tables.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_tables()

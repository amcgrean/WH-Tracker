from app.Services.erp_service import ERPService

def list_target_columns():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        tables = ['cust', 'cust_shipto', 'ship_to_address']
        
        with open('target_columns.txt', 'w') as f:
            for table in tables:
                f.write(f"\n--- Columns for {table} ---\n")
                query = f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}' ORDER BY COLUMN_NAME"
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    f.write(row[0] + '\n')
                
        conn.close()
        print("Done writing to target_columns.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_target_columns()

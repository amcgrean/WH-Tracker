from app.Services.erp_service import ERPService

def get_columns_schema():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'so_header'
            ORDER BY COLUMN_NAME
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        with open('so_header_columns_full.txt', 'w') as f:
            for row in rows:
                f.write(row[0] + '\n')
                
        conn.close()
        print("Done writing to so_header_columns_full.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_columns_schema()

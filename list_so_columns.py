from app.Services.erp_service import ERPService

def list_columns():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        print("Listing columns for so_header:")
        cursor.execute("SELECT TOP 0 * FROM so_header")
        columns = [column[0] for column in cursor.description]
        for col in sorted(columns):
            print(col)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_columns()

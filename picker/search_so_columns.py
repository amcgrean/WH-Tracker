from app.Services.erp_service import ERPService

def search_columns():
    erp = ERPService()
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT TOP 0 * FROM so_header")
        columns = [column[0].lower() for column in cursor.description]
        
        keywords = ['city', 'addr', 'cust', 'name', 'ship']
        found = []
        for col in columns:
            if any(k in col for k in keywords):
                found.append(col)
        
        with open('so_columns_found.txt', 'w') as f:
            for item in sorted(found):
                f.write(item + '\n')
                
        conn.close()
        print("Done writing to so_columns_found.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_columns()

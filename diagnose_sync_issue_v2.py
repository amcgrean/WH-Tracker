import os
from datetime import datetime
from dotenv import load_dotenv
from app.Services.erp_service import ERPService
from sqlalchemy import create_engine, text

load_dotenv()

def diagnose():
    erp = ERPService()
    print("--- Local ERP Check ---")
    try:
        conn = erp.get_connection()
        cursor = conn.cursor()
        
        # Check raw statuses in so_header
        print("Checking so_header statuses (Top 5):")
        cursor.execute("SELECT TOP 5 so_id, so_status, sale_type FROM so_header WHERE so_status != 'C'")
        for row in cursor.fetchall():
            print(f"SO: {row.so_id}, Status: '{row.so_status}', Type: '{row.sale_type}'")
            
        # Check if there are any 'k', 'p', 's' or 'K', 'P', 'S'
        cursor.execute("SELECT so_status, COUNT(*) FROM so_header GROUP BY so_status")
        print("\nStatus Counts:")
        for row in cursor.fetchall():
            print(f"Status: '{row[0]}', Count: {row[1]}")
            
        # Check if any match the query criteria
        today = datetime.now().strftime('%Y-%m-%d')
        print(f"\nChecking with today = {today}")
        
        # Test a simplified version of the filter
        cursor.execute(f"SELECT COUNT(*) FROM so_header WHERE so_status IN ('K', 'P', 'S', 'k', 'p', 's')")
        print(f"Count of K/P/S (both cases): {cursor.fetchone()[0]}")
        
        # Check sale_types
        cursor.execute("SELECT sale_type, COUNT(*) FROM so_header GROUP BY sale_type")
        print("\nSale Type Counts:")
        for row in cursor.fetchall():
            print(f"Type: '{row[0]}', Count: {row[1]}")
            
    except Exception as e:
        print(f"Local ERP Error: {e}")
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    diagnose()

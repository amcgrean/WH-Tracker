from app.Services.erp_service import ERPService
from datetime import datetime, timedelta

def test_kpi_comparison():
    erp = ERPService()
    
    query_invoice = """
        SELECT COUNT(DISTINCT soh.so_id) as count
        FROM so_header soh
        JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
        WHERE soh.so_status = 'I'
          AND sh.invoice_date = CAST(DATEADD(day, -5, GETDATE()) AS DATE)
          AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
    """
    
    query_ship = """
        SELECT COUNT(DISTINCT soh.so_id) as count
        FROM so_header soh
        JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
        WHERE sh.ship_date = CAST(DATEADD(day, -5, GETDATE()) AS DATE)
          AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
    """
    
    conn = erp.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(query_invoice)
    inv_count = cursor.fetchone()[0]
    
    cursor.execute(query_ship)
    ship_count = cursor.fetchone()[0]
    
    print(f"5 Days Ago Comparison:")
    print(f"  - Invoiced Orders (by Invoice Date): {inv_count}")
    print(f"  - Shipped Orders (by Ship Date): {ship_count}")
    conn.close()

if __name__ == "__main__":
    test_kpi_comparison()

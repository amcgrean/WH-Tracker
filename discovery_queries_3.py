import pyodbc
from dotenv import load_dotenv

load_dotenv()

def run_query(query, description, out_file):
    server = '10.1.1.17'
    database = 'AgilitySQL'
    username = 'amcgrean'
    password = 'Forgefrog69!'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        out_file.write(f"\n{'='*70}\n")
        out_file.write(f"--- {description} ---\n")
        
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        out_file.write(" | ".join(columns) + "\n")
        out_file.write("-" * 70 + "\n")
        
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                out_file.write(" | ".join([str(item) for item in row]) + "\n")
        else:
            out_file.write("No data found.\n")
            
        out_file.write(f"{'='*70}\n\n")
        conn.close()
    except Exception as e:
        out_file.write(f"Error querying {description}: {e}\n")

if __name__ == "__main__":
    with open("discovery_output_utf8_3.txt", "w", encoding="utf-8") as out:
        # Check shipments_header for load timeframe and route strings
        run_query(
            "SELECT TOP 5 so_id, shipment_num, ship_via, driver, route_id_char FROM shipments_header ORDER BY created_date DESC",
            "Shipments Header Mapping Columns", out
        )
        # Looking for timeframe
        run_query(
            "SELECT TOP 0 * FROM shipments_header",
            "Shipments Header ALL Columns", out
        )
        
        # Check print transaction for pick ticket times
        run_query(
            "SELECT TOP 5 * FROM print_transaction ORDER BY created_date DESC, created_time DESC",
            "Print Transaction Table", out
        )

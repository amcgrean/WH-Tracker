import pyodbc

server = '10.1.1.17'
database = 'AgilitySQL'
username = 'amcgrean'
password = 'Forgefrog69!'
driver = '{ODBC Driver 17 for SQL Server}'

try:
    conn = pyodbc.connect(f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}')
    cursor = conn.cursor()
    
    print("Distinct route_id_sysid:")
    cursor.execute("SELECT DISTINCT TOP 5 route_id_sysid FROM shipments_header WHERE route_id_sysid IS NOT NULL AND route_id_sysid != ''")
    print([r[0] for r in cursor.fetchall()])
    
    print("\nDistinct route_id_char:")
    cursor.execute("SELECT DISTINCT TOP 5 route_id_char FROM shipments_header WHERE route_id_char IS NOT NULL AND route_id_char != ''")
    print([r[0] for r in cursor.fetchall()])
    
    print("\nDistinct driver:")
    cursor.execute("SELECT DISTINCT TOP 5 driver FROM shipments_header WHERE driver IS NOT NULL AND driver != ''")
    print([r[0] for r in cursor.fetchall()])
    
    conn.close()
except Exception as e:
    print(e)

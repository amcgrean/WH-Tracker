import sqlite3
import os

db_path = r"C:\Users\amcgrean\python\tracker\picker\legacy pick db.db"

if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def print_table_info(table_name):
    print(f"\n--- Table: {table_name} ---")
    try:
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        if columns:
            for col in columns:
                print(col)
        else:
            print("Table not found or empty.")
    except Exception as e:
        print(f"Error inspecting {table_name}: {e}")

# Write output to file
with open("db_schema.txt", "w") as f:
    def log(msg):
        print(msg)
        f.write(str(msg) + "\n")

    # List all tables
    log("--- All Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    log(tables)

    def print_table_info_to_file(table_name):
        log(f"\n--- Table: {table_name} ---")
        try:
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            if columns:
                for col in columns:
                    log(col)
            else:
                log("Table not found or empty.")
        except Exception as e:
            log(f"Error inspecting {table_name}: {e}")

    # Inspect specific tables
    print_table_info_to_file('pickster')
    print_table_info_to_file('pick')
    print_table_info_to_file('PickTypes') # Checking if this exists in legacy

conn.close()

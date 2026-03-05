import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def update_schema():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if not url:
        print("DATABASE_URL not found")
        return
        
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(url)
    
    columns_to_add = [
        ("ship_via", "VARCHAR(128)"),
        ("driver", "VARCHAR(128)"),
        ("route", "VARCHAR(128)"),
        ("printed_at", "TIMESTAMP"),
        ("staged_at", "TIMESTAMP"),
        ("delivered_at", "TIMESTAMP"),
        ("local_pick_state", "VARCHAR(50)")
    ]
    
    with engine.connect() as conn:
        print("Updating erp_mirror_picks table...")
        for col_name, col_type in columns_to_add:
            try:
                # PostgreSQL specific: ADD COLUMN IF NOT EXISTS requires PG 9.6+
                query = f"ALTER TABLE erp_mirror_picks ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                conn.execute(text(query))
                print(f"  - Check/Add column: {col_name}")
            except Exception as e:
                print(f"  - Error adding {col_name}: {e}")
        
        conn.commit()
        print("Successfully updated schema.")

if __name__ == "__main__":
    update_schema()

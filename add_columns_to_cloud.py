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
    
    with engine.connect() as conn:
        print("Adding system_id and expect_date columns to erp_mirror_picks...")
        try:
            conn.execute(text("ALTER TABLE erp_mirror_picks ADD COLUMN IF NOT EXISTS system_id VARCHAR(50)"))
            conn.execute(text("ALTER TABLE erp_mirror_picks ADD COLUMN IF NOT EXISTS expect_date VARCHAR(50)"))
            conn.commit()
            print("Successfully updated schema.")
        except Exception as e:
            print(f"Error updating schema: {e}")

if __name__ == "__main__":
    update_schema()

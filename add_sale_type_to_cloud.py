import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def add_column():
    with engine.connect() as conn:
        print("Checking if sale_type column exists in erp_mirror_picks...")
        # Check if column exists
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='erp_mirror_picks' AND column_name='sale_type'
        """)
        result = conn.execute(check_query).fetchone()
        
        if not result:
            print("Adding sale_type column to erp_mirror_picks...")
            conn.execute(text("ALTER TABLE erp_mirror_picks ADD COLUMN sale_type VARCHAR(50)"))
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column sale_type already exists.")

if __name__ == "__main__":
    try:
        add_column()
    except Exception as e:
        print(f"Error: {e}")

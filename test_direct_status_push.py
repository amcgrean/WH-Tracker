import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import sys

# Add app directory to path
sys.path.append(os.getcwd())

from app.Models.models import ERPMirrorPick

def test_status_push():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        print("Testing Direct SQL Push for a single record with status...")
        # Clear one specific SO if it exists
        session.query(ERPMirrorPick).filter_by(so_number='TEST_STATUS').delete()
        
        new_pick = ERPMirrorPick(
            so_number='TEST_STATUS',
            customer_name='Test Corp',
            so_status='P',
            shipment_status='E',
            synced_at=None # will use default
        )
        session.add(new_pick)
        session.commit()
        print("Commit successful.")
        
        # Verify
        with engine.connect() as conn:
            result = conn.execute(text("SELECT so_number, so_status, shipment_status FROM erp_mirror_picks WHERE so_number = 'TEST_STATUS'"))
            row = result.fetchone()
            if row:
                print(f"VERIFIED in Cloud DB: SO={row[0]}, Status={row[1]}, ShipStatus={row[2]}")
            else:
                print("FAILED: Record not found in Cloud DB.")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    test_status_push()

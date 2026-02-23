import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from app.Models.models import ERPMirrorPick
from datetime import datetime

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(url)
Session = sessionmaker(bind=engine)
session = Session()

try:
    print("Attempting to delete all picks...")
    session.query(ERPMirrorPick).delete()
    
    print("Attempting to insert 1 test pick...")
    p = ERPMirrorPick(
        so_number='TEST-123',
        customer_name='Test Cust',
        address='123 Test St',
        reference='Ref',
        handling_code='HC',
        sequence=1,
        item_number='ITEM-1',
        description='Desc',
        qty=1.0,
        line_count=1,
        synced_at=datetime.utcnow()
    )
    session.add(p)
    session.commit()
    print("Test Push Successful!")
except Exception as e:
    session.rollback()
    print(f"Test Push Failed: {e}")
finally:
    session.close()

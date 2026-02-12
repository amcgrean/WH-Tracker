import sqlite3
import os
from datetime import datetime
from app import create_app, db
from app.Models.models import Pickster, Pick, PickTypes

# Paths
legacy_db_path = r"C:\Users\amcgrean\python\tracker\picker\legacy pick db.db"
new_db_instance = "instance/picker.db"

# Initialize App Context
app = create_app()

def run_import():
    if not os.path.exists(legacy_db_path):
        print(f"Legacy DB not found at: {legacy_db_path}")
        return

    print(f"Connecting to Legacy DB: {legacy_db_path}")
    legacy_conn = sqlite3.connect(legacy_db_path)
    legacy_conn.row_factory = sqlite3.Row
    cur = legacy_conn.cursor()

    with app.app_context():
        print("Starting Import...")
        
        # 1. Import PickTypes
        # -------------------
        print("\n--- Importing PickTypes ---")
        cur.execute("SELECT * FROM PickTypes")
        legacy_types = cur.fetchall()
        
        type_map = {} # Old ID -> New ID
        
        for row in legacy_types:
            old_id = row['pick_type_id']
            type_name = row['type_name']
            
            # Check if exists
            existing = PickTypes.query.filter_by(type_name=type_name).first()
            if existing:
                print(f"  Skipping existing type: {type_name} (ID: {existing.pick_type_id})")
                type_map[old_id] = existing.pick_type_id
            else:
                print(f"  Creating new type: {type_name}")
                new_type = PickTypes(type_name=type_name)
                db.session.add(new_type)
                db.session.flush() # Get ID
                type_map[old_id] = new_type.pick_type_id
        
        db.session.commit()

        # 2. Import Picksters
        # -------------------
        print("\n--- Importing Picksters ---")
        cur.execute("SELECT * FROM pickster")
        legacy_picksters = cur.fetchall()
        
        picker_map = {} # Old ID -> New ID
        
        for row in legacy_picksters:
            old_id = row['id']
            name = row['name']
            
            existing = Pickster.query.filter_by(name=name).first()
            if existing:
                 print(f"  Skipping existing user: {name} (ID: {existing.id})")
                 picker_map[old_id] = existing.id
            else:
                print(f"  Creating new user: {name}")
                new_user = Pickster(name=name, user_type='picker') # Default to picker
                db.session.add(new_user)
                db.session.flush()
                picker_map[old_id] = new_user.id
                
        db.session.commit()

        # 3. Import Picks
        # ---------------
        print("\n--- Importing Picks ---")
        cur.execute("SELECT * FROM pick")
        legacy_picks = cur.fetchall()
        
        added_count = 0
        skipped_count = 0
        
        for row in legacy_picks:
            # Format times
            start_time = datetime.strptime(row['start_time'], '%Y-%m-%d %H:%M:%S.%f') if row['start_time'] else None
            completed_time = datetime.strptime(row['completed_time'], '%Y-%m-%d %H:%M:%S.%f') if row['completed_time'] else None
            
            barcode = row['barcode_number']
            old_picker_id = row['picker_id']
            old_type_id = row['pick_type_id']
            
            # Map IDs
            new_picker_id = picker_map.get(old_picker_id)
            new_type_id = type_map.get(old_type_id)
            
            if not new_picker_id:
                print(f"  Warning: Could not map picker ID {old_picker_id} for pick {row['id']}. Skipping.")
                continue

            # Check for duplicates (simple check based on barcode + start_time)
            # This assumes start_time is unique enough
            exists = Pick.query.filter_by(
                barcode_number=barcode, 
                start_time=start_time, 
                picker_id=new_picker_id
            ).first()
            
            if exists:
                skipped_count += 1
            else:
                new_pick = Pick(
                    start_time=start_time,
                    completed_time=completed_time,
                    barcode_number=barcode,
                    picker_id=new_picker_id,
                    pick_type_id=new_type_id
                )
                db.session.add(new_pick)
                added_count += 1
                
                if added_count % 100 == 0:
                    print(f"  Imported {added_count} picks...")
                    db.session.commit()
        
        db.session.commit()
        print(f"\nImport Completed!")
        print(f"  Added:   {added_count}")
        print(f"  Skipped: {skipped_count}")

    legacy_conn.close()

if __name__ == "__main__":
    run_import()

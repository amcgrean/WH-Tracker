"""
seed_users.py
-------------
Seed initial AppUser records for WH-Tracker.

Usage:
    cd /path/to/WH-Tracker
    python scripts/seed_users.py

Edit the SEED_USERS list below before running.
Existing users (matched by email) are updated in place, not duplicated.

Rep ID (user_id) convention:
    - Use the employee's ERP login prefix, e.g. "mschmit" for Mike Schmidt.
    - This value flows into sales rep dashboards, open order filters, and PO views.
    - Leave blank ("") if the user doesn't have an ERP identity.
"""

import os
import sys

# Make sure the project root is on sys.path so imports work.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.Models.models import AppUser

# ---------------------------------------------------------------------------
# EDIT THIS LIST before running
# ---------------------------------------------------------------------------
SEED_USERS = [
    # Example Beisser users — replace with real data:
    {
        "email":        "admin@beisserlumber.com",
        "user_id":      "",          # no ERP rep ID for generic admin
        "display_name": "App Admin",
        "roles":        ["admin"],
        "phone":        "",          # leave blank, or "+16025551234" for phase 2
    },
    # Sales rep example — mschmit@BEISSERLUMBER.COM logs in and sees HIS orders
    {
        "email":        "mschmit@beisserlumber.com",
        "user_id":      "mschmit",
        "display_name": "Mike Schmidt",
        "roles":        ["sales"],
        "phone":        "",
    },
    # Ops manager — sees everything
    {
        "email":        "ops@beisserlumber.com",
        "user_id":      "",
        "display_name": "Ops Manager",
        "roles":        ["ops", "admin"],
        "phone":        "",
    },
    # Warehouse supervisor
    {
        "email":        "supervisor@beisserlumber.com",
        "user_id":      "",
        "display_name": "Warehouse Supervisor",
        "roles":        ["supervisor", "warehouse"],
        "phone":        "",
    },
    # Dispatcher
    {
        "email":        "dispatch@beisserlumber.com",
        "user_id":      "",
        "display_name": "Dispatch",
        "roles":        ["dispatch", "delivery"],
        "phone":        "",
    },
]
# ---------------------------------------------------------------------------


def seed():
    app = create_app()
    with app.app_context():
        created = 0
        updated = 0
        for data in SEED_USERS:
            email = data["email"].strip().lower()
            user = AppUser.query.filter_by(email=email).first()
            if user:
                user.user_id      = data.get("user_id") or None
                user.display_name = data.get("display_name") or None
                user.roles        = data.get("roles", [])
                user.phone        = data.get("phone") or None
                updated += 1
                print(f"  Updated : {email}  roles={user.roles}")
            else:
                user = AppUser(
                    email=email,
                    user_id=data.get("user_id") or None,
                    display_name=data.get("display_name") or None,
                    roles=data.get("roles", []),
                    phone=data.get("phone") or None,
                    is_active=True,
                )
                db.session.add(user)
                created += 1
                print(f"  Created : {email}  roles={user.roles}")

        db.session.commit()
        print(f"\nDone — {created} created, {updated} updated.")


if __name__ == "__main__":
    seed()

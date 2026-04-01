"""erp_mirror_item_supplier unique key — no-op (Pi-managed table)

erp_mirror_item_supplier is created and owned by the Pi sync worker, not the
Flask app. The live table has a different schema from the SQLAlchemy model
(item_ptr is INTEGER, unique key is on prrowid, etc.). Do not alter it here.

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-03-31 22:00:00.000000
"""

from alembic import op


revision = 's2t3u4v5w6x7'
down_revision = 'r1s2t3u4v5w6'
branch_labels = None
depends_on = None


def upgrade():
    pass  # Pi-managed table — no Flask-side DDL changes needed.


def downgrade():
    pass

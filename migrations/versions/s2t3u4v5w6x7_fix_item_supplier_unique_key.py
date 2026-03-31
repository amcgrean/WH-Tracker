"""Fix erp_mirror_item_supplier unique key to include system_id

The original constraint was on (item_ptr, supplier_key) only, which rejects
duplicate item-supplier pairs when the same pair exists in multiple branches.
Replace it with a functional unique index on
(COALESCE(system_id, ''), item_ptr, supplier_key) so per-branch rows coexist.

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-03-31 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 's2t3u4v5w6x7'
down_revision = 'r1s2t3u4v5w6'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the narrow two-column constraint
    op.drop_constraint(
        'uq_erp_mirror_item_supplier_key',
        'erp_mirror_item_supplier',
        type_='unique',
    )
    # Add functional unique index that treats NULL system_id as '' so two rows
    # with the same (item_ptr, supplier_key) but no system_id still conflict,
    # while rows for different branches can coexist.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_erp_mirror_item_supplier_key
        ON erp_mirror_item_supplier (COALESCE(system_id, ''), item_ptr, supplier_key)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_erp_mirror_item_supplier_key")
    op.create_unique_constraint(
        'uq_erp_mirror_item_supplier_key',
        'erp_mirror_item_supplier',
        ['item_ptr', 'supplier_key'],
    )

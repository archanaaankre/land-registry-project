"""Enforce uniqueness for normalized cadastral numbers.

Revision ID: c31e8f4a2d70
Revises: 2f14c6a90b31
"""
from alembic import op
import sqlalchemy as sa


revision = "c31e8f4a2d70"
down_revision = "2f14c6a90b31"
branch_labels = None
depends_on = None


def _assert_unique_cadastral_numbers(connection):
    rows = connection.execute(
        sa.text("SELECT parcel_id, cadastral_number FROM parcels")
    )
    seen = set()
    duplicates_found = False
    for _, cadastral_number in rows:
        normalized = cadastral_number.strip().upper()
        if normalized in seen:
            duplicates_found = True
            break
        seen.add(normalized)
    if duplicates_found:
        raise RuntimeError(
            "Cannot add the cadastral-number uniqueness index: existing parcel "
            "records contain duplicate values after trimming whitespace and "
            "converting to uppercase. Review and resolve the conflicting records "
            "manually; this migration does not modify parcel data."
        )


def upgrade():
    _assert_unique_cadastral_numbers(op.get_bind())
    op.create_index(
        "uq_parcels_cadastral_number_normalized",
        "parcels",
        [sa.text("upper(trim(cadastral_number))")],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_parcels_cadastral_number_normalized",
        table_name="parcels",
    )

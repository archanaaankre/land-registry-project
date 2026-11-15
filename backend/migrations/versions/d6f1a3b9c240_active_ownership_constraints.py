"""Protect active ownership records and shares.

Revision ID: d6f1a3b9c240
Revises: c31e8f4a2d70
"""
from collections import defaultdict
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "d6f1a3b9c240"
down_revision = "c31e8f4a2d70"
branch_labels = None
depends_on = None


def _assert_active_ownership_invariants(connection):
    rows = connection.execute(
        sa.text(
            "SELECT parcel_id, owner_id, share FROM ownerships "
            "WHERE status = 'ACTIVE'"
        )
    )
    shares_by_parcel = defaultdict(Decimal)
    owners_by_parcel = set()
    duplicate_owner_found = False

    for parcel_id, owner_id, share in rows:
        key = (parcel_id, owner_id)
        if key in owners_by_parcel:
            duplicate_owner_found = True
        owners_by_parcel.add(key)
        shares_by_parcel[parcel_id] += Decimal(str(share))

    overallocated_parcels = [
        parcel_id
        for parcel_id, share in shares_by_parcel.items()
        if share > Decimal("100")
    ]
    if duplicate_owner_found or overallocated_parcels:
        problems = []
        if duplicate_owner_found:
            problems.append("duplicate active parcel-owner records")
        if overallocated_parcels:
            problems.append(
                "active shares above 100% for parcel(s): "
                + ", ".join(sorted(overallocated_parcels))
            )
        raise RuntimeError(
            "Cannot add active ownership constraints because existing data has "
            + " and ".join(problems)
            + ". Review and resolve the records manually; this migration does "
            "not modify ownership data."
        )


def upgrade():
    _assert_active_ownership_invariants(op.get_bind())
    op.create_index(
        "uq_ownerships_one_active_owner_per_parcel",
        "ownerships",
        ["parcel_id", "owner_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade():
    op.drop_index(
        "uq_ownerships_one_active_owner_per_parcel",
        table_name="ownerships",
    )

"""Ensure a parcel has at most one active transfer request.

Revision ID: 2f14c6a90b31
Revises: a8a1c8b2698b
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa


revision = "2f14c6a90b31"
down_revision = "a8a1c8b2698b"
branch_labels = None
depends_on = None


_ACTIVE_STATUSES = sa.text(
    "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','BLOCKCHAIN_PENDING')"
)


def upgrade():
    op.create_index(
        "uq_transfer_requests_one_active_per_parcel",
        "transfer_requests",
        ["parcel_id"],
        unique=True,
        postgresql_where=_ACTIVE_STATUSES,
        sqlite_where=_ACTIVE_STATUSES,
    )


def downgrade():
    op.drop_index(
        "uq_transfer_requests_one_active_per_parcel",
        table_name="transfer_requests",
    )

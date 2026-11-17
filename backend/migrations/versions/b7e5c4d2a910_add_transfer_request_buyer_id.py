"""Add canonical buyer identity to transfer requests.

Revision ID: b7e5c4d2a910
Revises: f6b6ebf8c7d9
"""
from alembic import op
import sqlalchemy as sa


revision = "b7e5c4d2a910"
down_revision = "f6b6ebf8c7d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transfer_requests",
        sa.Column(
            "buyer_id",
            sa.String(length=128),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_transfer_requests_buyer_id",
        "transfer_requests",
        ["buyer_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_transfer_requests_buyer_id",
        table_name="transfer_requests",
    )
    op.drop_column("transfer_requests", "buyer_id")

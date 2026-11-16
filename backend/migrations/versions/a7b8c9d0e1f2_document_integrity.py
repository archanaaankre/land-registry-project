"""Create document_hashes table for integrity verification.

Revision ID: a7b8c9d0e1f2
Revises: f4a2b9c1d6e3
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f4a2b9c1d6e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_hashes",
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("parcel_id", sa.String(length=64), nullable=True),
        sa.Column("document_name", sa.String(length=200), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=128), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_count", sa.Integer(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_verification_status", sa.String(length=16), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["parcel_id"], ["parcels.parcel_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index(
        op.f("ix_document_hashes_parcel_id"),
        "document_hashes",
        ["parcel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_hashes_uploaded_by"),
        "document_hashes",
        ["uploaded_by"],
        unique=False,
    )
    op.create_index(
        "uq_document_hashes_name_per_parcel",
        "document_hashes",
        ["document_name", "parcel_id"],
        unique=True,
        postgresql_where=sa.text("parcel_id IS NOT NULL"),
        sqlite_where=sa.text("parcel_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_document_hashes_name_per_parcel",
        table_name="document_hashes",
    )
    op.drop_index(op.f("ix_document_hashes_uploaded_by"), table_name="document_hashes")
    op.drop_index(op.f("ix_document_hashes_parcel_id"), table_name="document_hashes")
    op.drop_table("document_hashes")

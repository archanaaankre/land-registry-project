"""Create supporting_documents table.

Revision ID: d8e4b9a2f6c7
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "d8e4b9a2f6c7"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None

_TABLE = "supporting_documents"


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("supporting_document_id", sa.String(length=64), nullable=False),
            sa.Column("parcel_id", sa.String(length=64), nullable=True),
            sa.Column("transfer_request_id", sa.String(length=64), nullable=True),
            sa.Column("document_name", sa.String(length=200), nullable=False),
            sa.Column("document_hash", sa.String(length=64), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("uploaded_by", sa.String(length=128), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["parcel_id"], ["parcels.parcel_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["transfer_request_id"], ["transfer_requests.request_id"]
            ),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("supporting_document_id"),
        )
    insp = sa.inspect(op.get_bind())
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name, columns in (
        ("ix_supporting_documents_parcel_id", ["parcel_id"]),
        ("ix_supporting_documents_transfer_request_id", ["transfer_request_id"]),
        ("ix_supporting_documents_uploaded_by", ["uploaded_by"]),
    ):
        if name not in existing:
            op.create_index(name, _TABLE, columns)


def downgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name in (
        "ix_supporting_documents_parcel_id",
        "ix_supporting_documents_transfer_request_id",
        "ix_supporting_documents_uploaded_by",
    ):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)

"""Create document_hashes table for integrity verification (defensive).

Revision ID: a7b8c9d0e1f2
Revises: f4a2b9c1d6e3

Defensive: if the table already exists (e.g. a partially upgraded database),
only the missing indexes are created; the table is left untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f4a2b9c1d6e3"
branch_labels = None
depends_on = None

_TABLE = "document_hashes"
_INDEXES = (
    ("ix_document_hashes_parcel_id", ["parcel_id"], False, None),
    ("ix_document_hashes_uploaded_by", ["uploaded_by"], False, None),
    (
        "uq_document_hashes_name_per_parcel",
        ["document_name", "parcel_id"],
        True,
        sa.text("parcel_id IS NOT NULL"),
    ),
)


def _create_table():
    op.create_table(
        _TABLE,
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("parcel_id", sa.String(length=64), nullable=True),
        sa.Column("document_name", sa.String(length=200), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=128), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_count", sa.Integer(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verification_status", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.parcel_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("document_id"),
    )


def _create_index(name, columns, unique, where):
    kwargs = {"unique": unique}
    if where is not None:
        kwargs["postgresql_where"] = where
        kwargs["sqlite_where"] = where
    op.create_index(name, _TABLE, columns, **kwargs)


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        _create_table()
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name, columns, unique, where in _INDEXES:
        if name not in existing:
            _create_index(name, columns, unique, where)


def downgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name, _columns, _unique, _where in reversed(_INDEXES):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)

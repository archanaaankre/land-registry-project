"""Add canonical buyer identity to transfer requests (defensive).

Revision ID: b7e5c4d2a910
Revises: f6b6ebf8c7d9

This column exists only on the Person 1 migration branch; Person 2's model
declares it but has no migration for it. Guarded so a partially upgraded
database is not broken by duplicate column/index creation.
"""
from alembic import op
import sqlalchemy as sa


revision = "b7e5c4d2a910"
down_revision = "f6b6ebf8c7d9"
branch_labels = None
depends_on = None

_TABLE = "transfer_requests"
_COLUMN = "buyer_id"
_INDEX = "ix_transfer_requests_buyer_id"


def upgrade():
    insp = sa.inspect(op.get_bind())
    columns = {column["name"] for column in insp.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(length=128),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )
    indexes = {index["name"] for index in insp.get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)


def downgrade():
    insp = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in insp.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = {column["name"] for column in insp.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)

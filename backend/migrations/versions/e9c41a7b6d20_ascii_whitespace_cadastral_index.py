"""Use the same edge-whitespace policy for cadastral uniqueness.

Revision ID: e9c41a7b6d20
Revises: d6f1a3b9c240
"""
from alembic import op
import sqlalchemy as sa


revision = "e9c41a7b6d20"
down_revision = "d6f1a3b9c240"
branch_labels = None
depends_on = None

_EDGE_WHITESPACE = " \t\n\r\v\f"
_EDGE_WHITESPACE_SQL = f"'{_EDGE_WHITESPACE}'"
_NORMALIZED_CADASTRAL_EXPRESSION = (
    "upper(ltrim(rtrim(cadastral_number, "
    f"{_EDGE_WHITESPACE_SQL}), {_EDGE_WHITESPACE_SQL}))"
)


def _normalize_cadastral_number(value):
    return value.strip(_EDGE_WHITESPACE).upper()


def _assert_unique_normalized_cadastral_numbers(connection):
    rows = connection.execute(
        sa.text("SELECT parcel_id, cadastral_number FROM parcels")
    )
    seen = set()
    for parcel_id, cadastral_number in rows:
        normalized = _normalize_cadastral_number(cadastral_number)
        if normalized in seen:
            raise RuntimeError(
                "Cannot replace the cadastral-number uniqueness index: existing "
                "parcel records contain duplicate values after trimming ASCII "
                "edge whitespace (space, tab, LF, CR, vertical tab, form feed) "
                "and converting to uppercase. Review and resolve the conflicting "
                f"records manually; parcel {parcel_id!r} is not modified."
            )
        seen.add(normalized)


def upgrade():
    connection = op.get_bind()
    _assert_unique_normalized_cadastral_numbers(connection)
    op.create_index(
        "uq_parcels_cadastral_number_ascii_whitespace",
        "parcels",
        [sa.text(_NORMALIZED_CADASTRAL_EXPRESSION)],
        unique=True,
    )
    op.drop_index(
        "uq_parcels_cadastral_number_normalized",
        table_name="parcels",
    )


def downgrade():
    op.create_index(
        "uq_parcels_cadastral_number_normalized",
        "parcels",
        [sa.text("upper(trim(cadastral_number))")],
        unique=True,
    )
    op.drop_index(
        "uq_parcels_cadastral_number_ascii_whitespace",
        table_name="parcels",
    )

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.persistence.models import ParcelModel


def _migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "d6f1a3b9c240_active_ownership_constraints.py"
    )
    spec = importlib.util.spec_from_file_location(
        "active_ownership_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.parametrize(
    "ownership_rows",
    [
        [
            ("parcel-1", "citizen-1", 60),
            ("parcel-1", "citizen-1", 40),
        ],
        [
            ("parcel-1", "citizen-1", 60),
            ("parcel-1", "citizen-2", 40.000001),
        ],
    ],
)
def test_active_ownership_migration_refuses_invalid_legacy_data(
    tmp_path, ownership_rows
):
    engine = sa.create_engine(
        "sqlite:///" + str(tmp_path / "ownership_legacy.db").replace("\\", "/")
    )
    migration = _migration()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE ownerships "
                "(parcel_id VARCHAR(64), owner_id VARCHAR(128), "
                "share NUMERIC(20, 6), status VARCHAR(16))"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO ownerships (parcel_id, owner_id, share, status) "
                "VALUES (:parcel_id, :owner_id, :share, 'ACTIVE')"
            ),
            [
                {
                    "parcel_id": parcel_id,
                    "owner_id": owner_id,
                    "share": share,
                }
                for parcel_id, owner_id, share in ownership_rows
            ],
        )

        with pytest.raises(RuntimeError, match="does not modify ownership data"):
            migration._assert_active_ownership_invariants(connection)

        count = connection.execute(
            sa.text("SELECT COUNT(*) FROM ownerships")
        ).scalar_one()

    engine.dispose()
    assert count == len(ownership_rows)


def test_postgresql_row_lock_is_available_for_atomic_share_validation():
    statement = sa.select(ParcelModel).where(
        ParcelModel.parcel_id == "parcel-1"
    ).with_for_update()

    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))

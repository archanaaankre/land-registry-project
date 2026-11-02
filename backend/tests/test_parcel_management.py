import secrets
import importlib.util
from pathlib import Path
from decimal import Decimal

import pytest

from app import create_app, db
from app.auth.service import create_access_token
from app.config import Config
from app.models import ParcelStatus, Role, AreaUnit, utc_now
from app.persistence.models import ParcelModel
from app.persistence.repositories import SqlAlchemyParcelRepository


@pytest.fixture
def app(tmp_path, monkeypatch):
    database_url = "sqlite:///" + str(tmp_path / "parcel_management.db").replace(
        "\\", "/"
    )
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", database_url)
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
    )
    with application.app_context():
        db.create_all()
    application.config["PARCEL_REPOSITORY"] = SqlAlchemyParcelRepository()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def bearer(app, role):
    token = create_access_token(
        f"{role.value.lower()}-parcel-test", role, app.config["JWT_SECRET_KEY"]
    )
    return {"Authorization": f"Bearer {token}"}


def parcel_payload(parcel_id, cadastral_number, **updates):
    return {
        "parcel_id": parcel_id,
        "cadastral_number": cadastral_number,
        "location": "Ward 1",
        "area": 10,
        "area_unit": "HECTARES",
        "status": "ACTIVE",
        **updates,
    }


def register_parcel(client, app, parcel_id, cadastral_number, **updates):
    return client.post(
        "/api/parcels",
        headers=bearer(app, Role.REGISTRAR),
        json=parcel_payload(parcel_id, cadastral_number, **updates),
    )


def test_valid_creation_normalizes_cadastral_number(client, app):
    response = register_parcel(client, app, "parcel-1", "  cad-001  ")

    assert response.status_code == 201
    assert response.get_json()["parcel"]["cadastral_number"] == "CAD-001"


@pytest.mark.parametrize(
    "duplicate_value",
    [
        "  cad-001  ",
        "\tcad-001\t",
        "\ncad-001\r",
        "\vcad-001\f",
        " \t\nCaD-001\r\n ",
    ],
)
def test_duplicate_cadastral_number_is_rejected_without_changing_original(
    client, app, duplicate_value
):
    created = register_parcel(client, app, "parcel-1", "CAD-001")
    duplicate = register_parcel(
        client, app, "parcel-2", duplicate_value
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "conflict"
    original = client.get(
        "/api/parcels/parcel-1", headers=bearer(app, Role.CITIZEN)
    )
    assert original.status_code == 200
    assert original.get_json()["parcel"]["cadastral_number"] == "CAD-001"
    assert client.get(
        "/api/parcels/parcel-2", headers=bearer(app, Role.CITIZEN)
    ).status_code == 404


@pytest.mark.parametrize(
    ("input_value", "expected_value"),
    [
        ("  cad-space  ", "CAD-SPACE"),
        ("\tcad-tab\t", "CAD-TAB"),
        ("\ncad-newline\r", "CAD-NEWLINE"),
        ("\vcad-control\f", "CAD-CONTROL"),
    ],
)
def test_cadastral_number_normalizes_ascii_edge_whitespace(
    client, app, input_value, expected_value
):
    response = register_parcel(client, app, "parcel-normalized", input_value)

    assert response.status_code == 201
    assert response.get_json()["parcel"]["cadastral_number"] == expected_value


def test_database_index_rejects_unvalidated_whitespace_duplicate(app):
    from sqlalchemy.exc import IntegrityError

    now = utc_now()
    with app.app_context():
        db.session.add(
            ParcelModel(
                parcel_id="parcel-db-first",
                cadastral_number="CAD-DB",
                location="Ward 1",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES.value,
                status=ParcelStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
        )
        db.session.commit()
        db.session.add(
            ParcelModel(
                parcel_id="parcel-db-duplicate",
                cadastral_number="\tCAD-DB\n",
                location="Ward 2",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES.value,
                status=ParcelStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        assert db.session.get(ParcelModel, "parcel-db-first") is not None
        assert db.session.get(ParcelModel, "parcel-db-duplicate") is None


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.ADMIN])
def test_non_registrar_cannot_register_parcel(client, app, role):
    response = client.post(
        "/api/parcels",
        headers=bearer(app, role),
        json=parcel_payload("parcel-1", "CAD-001"),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_invalid_parcel_creation_is_rejected(client, app):
    response = client.post(
        "/api/parcels",
        headers=bearer(app, Role.REGISTRAR),
        json=parcel_payload("parcel-1", "CAD-001", area=-1),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_registrar_can_update_permitted_fields_without_changing_status_or_identity(
    client, app
):
    created = register_parcel(client, app, "parcel-1", "CAD-001")
    original = created.get_json()["parcel"]

    updated = client.patch(
        "/api/parcels/parcel-1",
        headers=bearer(app, Role.REGISTRAR),
        json={
            "cadastral_number": " cad-002 ",
            "location": "Ward 2",
            "area": 12.5,
            "area_unit": "ACRES",
        },
    )

    assert updated.status_code == 200
    parcel = updated.get_json()["parcel"]
    assert parcel["parcel_id"] == original["parcel_id"]
    assert parcel["created_at"] == original["created_at"]
    assert parcel["cadastral_number"] == "CAD-002"
    assert parcel["location"] == "Ward 2"
    assert parcel["area"] == "12.500000"
    assert parcel["area_unit"] == "ACRES"
    assert parcel["status"] == "ACTIVE"


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.ADMIN])
def test_non_registrar_cannot_update_parcel(client, app, role):
    register_parcel(client, app, "parcel-1", "CAD-001")

    response = client.patch(
        "/api/parcels/parcel-1",
        headers=bearer(app, role),
        json={"location": "Unauthorized"},
    )

    assert response.status_code == 403
    assert client.get(
        "/api/parcels/parcel-1", headers=bearer(app, Role.CITIZEN)
    ).get_json()["parcel"]["location"] == "Ward 1"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"area": 0},
        {"area": 1.1234567},
        {"area_unit": "SQUARE_FEET"},
        {"status": "UNKNOWN"},
        {"owner_id": "citizen-1"},
    ],
)
def test_invalid_or_non_parcel_update_fields_are_rejected(client, app, payload):
    register_parcel(client, app, "parcel-1", "CAD-001")

    response = client.patch(
        "/api/parcels/parcel-1",
        headers=bearer(app, Role.REGISTRAR),
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_update_rejects_duplicate_cadastral_number_and_keeps_record_intact(
    client, app
):
    register_parcel(client, app, "parcel-1", "CAD-001")
    register_parcel(client, app, "parcel-2", "CAD-002")

    response = client.patch(
        "/api/parcels/parcel-2",
        headers=bearer(app, Role.REGISTRAR),
        json={"cadastral_number": " cad-001 "},
    )

    assert response.status_code == 409
    unchanged = client.get(
        "/api/parcels/parcel-2", headers=bearer(app, Role.CITIZEN)
    ).get_json()["parcel"]
    assert unchanged["cadastral_number"] == "CAD-002"
    assert unchanged["location"] == "Ward 1"


def test_status_transition_and_validation(client, app):
    register_parcel(client, app, "parcel-1", "CAD-001")

    disputed = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, Role.REGISTRAR),
        json={"status": "DISPUTED"},
    )
    assert disputed.status_code == 200
    assert disputed.get_json()["parcel"]["status"] == "DISPUTED"

    inactive = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, Role.REGISTRAR),
        json={"status": "INACTIVE"},
    )
    assert inactive.status_code == 200
    assert inactive.get_json()["parcel"]["status"] == "INACTIVE"

    invalid = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, Role.REGISTRAR),
        json={"status": "ARCHIVED"},
    )
    repeated = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, Role.REGISTRAR),
        json={"status": "INACTIVE"},
    )
    assert invalid.status_code == 400
    assert repeated.status_code == 409


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.ADMIN])
def test_non_registrar_cannot_change_parcel_status(client, app, role):
    register_parcel(client, app, "parcel-1", "CAD-001")

    response = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, role),
        json={"status": "DISPUTED"},
    )

    assert response.status_code == 403


def test_status_endpoint_rejects_extra_fields_and_invalid_json_shape(client, app):
    register_parcel(client, app, "parcel-1", "CAD-001")

    response = client.patch(
        "/api/parcels/parcel-1/status",
        headers=bearer(app, Role.REGISTRAR),
        json={"status": "DISPUTED", "owner_id": "citizen-1"},
    )

    assert response.status_code == 400


def test_search_filters_by_cadastral_number_location_and_status(client, app):
    register_parcel(
        client, app, "parcel-1", "CAD-001", location="North District"
    )
    register_parcel(
        client, app, "parcel-2", "CAD-002", location="South District"
    )
    register_parcel(
        client,
        app,
        "parcel-3",
        "CAD-003",
        location="North Borough",
        status="DISPUTED",
    )

    cadastral = client.get(
        "/api/parcels?cadastral_number=cad-00",
        headers=bearer(app, Role.CITIZEN),
    )
    location = client.get(
        "/api/parcels?location=nOrTh",
        headers=bearer(app, Role.CITIZEN),
    )
    status = client.get(
        "/api/parcels?status=DISPUTED",
        headers=bearer(app, Role.CITIZEN),
    )
    combined = client.get(
        "/api/parcels?search=north&status=ACTIVE",
        headers=bearer(app, Role.CITIZEN),
    )

    assert len(cadastral.get_json()["items"]) == 3
    assert {p["parcel_id"] for p in location.get_json()["items"]} == {
        "parcel-1",
        "parcel-3",
    }
    assert [p["parcel_id"] for p in status.get_json()["items"]] == ["parcel-3"]
    assert [p["parcel_id"] for p in combined.get_json()["items"]] == ["parcel-1"]


def test_search_pagination_and_boundaries(client, app):
    for index in range(5):
        response = register_parcel(
            client,
            app,
            f"parcel-{index}",
            f"CAD-{index}",
        )
        assert response.status_code == 201

    first_page = client.get(
        "/api/parcels?page=1&page_size=2",
        headers=bearer(app, Role.CITIZEN),
    )
    second_page = client.get(
        "/api/parcels?page=2&page_size=2",
        headers=bearer(app, Role.CITIZEN),
    )
    beyond_last_page = client.get(
        "/api/parcels?page=4&page_size=2",
        headers=bearer(app, Role.CITIZEN),
    )
    invalid_page = client.get(
        "/api/parcels?page=0", headers=bearer(app, Role.CITIZEN)
    )
    invalid_size = client.get(
        "/api/parcels?page_size=101", headers=bearer(app, Role.CITIZEN)
    )

    assert [p["parcel_id"] for p in first_page.get_json()["items"]] == [
        "parcel-0",
        "parcel-1",
    ]
    assert [p["parcel_id"] for p in second_page.get_json()["items"]] == [
        "parcel-2",
        "parcel-3",
    ]
    assert first_page.get_json()["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 5,
        "pages": 3,
    }
    assert beyond_last_page.get_json()["items"] == []
    assert beyond_last_page.get_json()["pagination"]["pages"] == 3
    assert invalid_page.status_code == 400
    assert invalid_size.status_code == 400


def test_existing_parcel_records_are_preserved_by_updates(client, app):
    created = register_parcel(
        client,
        app,
        "parcel-1",
        "CAD-001",
        location="Original Location",
    ).get_json()["parcel"]

    response = client.patch(
        "/api/parcels/parcel-1",
        headers=bearer(app, Role.REGISTRAR),
        json={"location": "Updated Location"},
    )
    result = response.get_json()["parcel"]

    assert response.status_code == 200
    assert result["parcel_id"] == created["parcel_id"]
    assert result["cadastral_number"] == created["cadastral_number"]
    assert result["area"] == created["area"]
    assert result["area_unit"] == created["area_unit"]
    assert result["created_at"] == created["created_at"]
    assert result["location"] == "Updated Location"


@pytest.mark.parametrize(
    "duplicate_values",
    [
        ("CAD-001", " cad-001 "),
        ("CAD-001", "\tcad-001\t"),
        ("CAD-001", "\ncad-001\r"),
        ("CAD-001", "\vcad-001\f"),
    ],
)
def test_migration_refuses_normalized_duplicates_without_modifying_records(
    tmp_path, duplicate_values
):
    import sqlalchemy as sa

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "c31e8f4a2d70_unique_normalized_cadastral_number.py"
    )
    spec = importlib.util.spec_from_file_location(
        "cadastral_number_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///" + str(tmp_path / "legacy.db"))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE parcels "
                "(parcel_id VARCHAR(64), cadastral_number VARCHAR(100))"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO parcels (parcel_id, cadastral_number) "
                "VALUES (:first_id, :first_value), (:second_id, :second_value)"
            ),
            {
                "first_id": "parcel-1",
                "first_value": duplicate_values[0],
                "second_id": "parcel-2",
                "second_value": duplicate_values[1],
            },
        )

        with pytest.raises(RuntimeError, match="does not modify parcel data"):
            migration._assert_unique_cadastral_numbers(connection)

        rows = connection.execute(
            sa.text("SELECT parcel_id, cadastral_number FROM parcels ORDER BY parcel_id")
        ).all()

    engine.dispose()
    assert rows == [
        ("parcel-1", duplicate_values[0]),
        ("parcel-2", duplicate_values[1]),
    ]


@pytest.mark.parametrize(
    "duplicate_values",
    [
        ("CAD-001", " cad-001 "),
        ("CAD-001", "\tcad-001\t"),
        ("CAD-001", "\ncad-001\r"),
        ("CAD-001", "\vcad-001\f"),
    ],
)
def test_updated_migration_detects_duplicates_without_modifying_records(
    tmp_path, duplicate_values
):
    import sqlalchemy as sa

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "e9c41a7b6d20_ascii_whitespace_cadastral_index.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ascii_whitespace_cadastral_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///" + str(tmp_path / "legacy_ascii.db"))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE parcels "
                "(parcel_id VARCHAR(64), cadastral_number VARCHAR(100))"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO parcels (parcel_id, cadastral_number) "
                "VALUES (:first_id, :first_value), (:second_id, :second_value)"
            ),
            {
                "first_id": "parcel-1",
                "first_value": duplicate_values[0],
                "second_id": "parcel-2",
                "second_value": duplicate_values[1],
            },
        )

        with pytest.raises(RuntimeError, match="not modified"):
            migration._assert_unique_normalized_cadastral_numbers(connection)

        rows = connection.execute(
            sa.text(
                "SELECT parcel_id, cadastral_number FROM parcels ORDER BY parcel_id"
            )
        ).all()

    engine.dispose()
    assert rows == [
        ("parcel-1", duplicate_values[0]),
        ("parcel-2", duplicate_values[1]),
    ]

from datetime import datetime, timezone
from decimal import Decimal
import secrets
from unittest.mock import Mock

import pytest

from app import create_app
from app.auth.decorators import roles_required
from app.auth.service import create_access_token
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
)
from app.registry.authorization import (
    OWNERSHIP_READ_ROLES,
    OWNERSHIP_RECORD_ROLES,
    PARCEL_MANAGE_ROLES,
    PARCEL_READ_ROLES,
)
from app.routes import _ownership_response, _parcel_response


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
    )

    @application.get("/api/test-parcel-management")
    @roles_required(*PARCEL_MANAGE_ROLES)
    def manage_parcels():
        return {"status": "authorized"}

    return application


@pytest.fixture
def client(app):
    return app.test_client()


def bearer(app, role):
    token = create_access_token(
        f"{role.value.lower()}-1", role, app.config["JWT_SECRET_KEY"]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("path", "roles"),
    [
        ("/api/parcels", PARCEL_READ_ROLES),
        ("/api/parcels/parcel-1", PARCEL_READ_ROLES),
        ("/api/parcels/parcel-1/ownership", OWNERSHIP_READ_ROLES),
    ],
)
def test_read_contracts_authorize_all_roles_then_report_unavailable(
    app, client, path, roles
):
    for role in roles:
        response = client.get(path, headers=bearer(app, role))
        assert response.status_code == 503
        assert response.get_json()["error"]["code"] == "registry_unavailable"


@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        ({}, "missing_authentication"),
        ({"Authorization": "Bearer invalid"}, "invalid_token"),
    ],
)
def test_parcel_read_contract_rejects_missing_or_invalid_authentication(
    client, headers, expected_code
):
    response = client.get("/api/parcels", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == expected_code


def test_invalid_parcel_reference_returns_clean_validation_error(app, client):
    response = client.get(
        "/api/parcels/invalid%21", headers=bearer(app, Role.CITIZEN)
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_only_registrar_is_authorized_for_registry_management(app, client):
    registrar = client.get(
        "/api/test-parcel-management", headers=bearer(app, Role.REGISTRAR)
    )
    citizen = client.get(
        "/api/test-parcel-management", headers=bearer(app, Role.CITIZEN)
    )
    admin = client.get(
        "/api/test-parcel-management", headers=bearer(app, Role.ADMIN)
    )

    assert registrar.status_code == 200
    assert citizen.status_code == 403
    assert admin.status_code == 403


def test_registrar_can_create_parcel(app, client):
    repository = Mock()
    repository.create_parcel.side_effect = lambda parcel: parcel
    app.config["PARCEL_REPOSITORY"] = repository

    response = client.post(
        "/api/parcels",
        headers=bearer(app, Role.REGISTRAR),
        json={
            "parcel_id": "parcel-1",
            "cadastral_number": "CAD-1",
            "location": "Ward 1",
            "area": 10,
            "area_unit": "HECTARES",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["parcel"]["parcel_id"] == "parcel-1"
    repository.create_parcel.assert_called_once()


def test_registrar_can_record_ownership_for_existing_parcel(app, client):
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = Parcel(
        parcel_id="parcel-1",
        cadastral_number="CAD-1",
        location="Ward 1",
        area=Decimal("10"),
        area_unit=AreaUnit.HECTARES,
        status=ParcelStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    ownership_repository = Mock()
    ownership_repository.create_ownership.side_effect = lambda ownership: ownership
    app.config["PARCEL_REPOSITORY"] = parcel_repository
    app.config["OWNERSHIP_REPOSITORY"] = ownership_repository

    response = client.post(
        "/api/ownership",
        headers=bearer(app, Role.REGISTRAR),
        json={
            "ownership_id": "ownership-1",
            "parcel_id": "parcel-1",
            "owner_id": "citizen-1",
            "share": 100,
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["ownership"]["owner_id"] == "citizen-1"
    parcel_repository.find_by_id.assert_called_once_with("parcel-1")
    ownership_repository.create_ownership.assert_called_once()


@pytest.mark.parametrize(
    ("role", "path", "payload"),
    [
        (
            Role.CITIZEN,
            "/api/parcels",
            {
                "parcel_id": "parcel-1",
                "cadastral_number": "CAD-1",
                "location": "Ward 1",
                "area": 10,
                "area_unit": "HECTARES",
                "status": "ACTIVE",
            },
        ),
        (
            Role.CITIZEN,
            "/api/ownership",
            {
                "ownership_id": "ownership-1",
                "parcel_id": "parcel-1",
                "owner_id": "citizen-1",
                "share": 100,
                "status": "ACTIVE",
            },
        ),
        (
            Role.ADMIN,
            "/api/parcels",
            {
                "parcel_id": "parcel-1",
                "cadastral_number": "CAD-1",
                "location": "Ward 1",
                "area": 10,
                "area_unit": "HECTARES",
                "status": "ACTIVE",
            },
        ),
        (
            Role.ADMIN,
            "/api/ownership",
            {
                "ownership_id": "ownership-1",
                "parcel_id": "parcel-1",
                "owner_id": "citizen-1",
                "share": 100,
                "status": "ACTIVE",
            },
        ),
    ],
)
def test_non_registrar_cannot_create_parcels_or_ownership(
    client, app, role, path, payload
):
    response = client.post(
        path, headers=bearer(app, role), json=payload
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_parcel_creation_rejects_invalid_data(app, client):
    response = client.post(
        "/api/parcels",
        headers=bearer(app, Role.REGISTRAR),
        json={
            "parcel_id": "parcel-1",
            "cadastral_number": "CAD-1",
            "location": "Ward 1",
            "area": 0,
            "area_unit": "HECTARES",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_ownership_creation_rejects_nonexistent_parcel(app, client):
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = None
    app.config["PARCEL_REPOSITORY"] = parcel_repository
    app.config["OWNERSHIP_REPOSITORY"] = Mock()

    response = client.post(
        "/api/ownership",
        headers=bearer(app, Role.REGISTRAR),
        json={
            "ownership_id": "ownership-1",
            "parcel_id": "missing-parcel",
            "owner_id": "citizen-1",
            "share": 100,
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"
    parcel_repository.find_by_id.assert_called_once_with("missing-parcel")


def test_ownership_record_policy_allows_only_registrar():
    assert OWNERSHIP_RECORD_ROLES == (Role.REGISTRAR,)


def test_read_role_policy_supports_citizen_registrar_and_admin():
    assert set(PARCEL_READ_ROLES) == set(Role)
    assert set(OWNERSHIP_READ_ROLES) == set(Role)
    assert PARCEL_MANAGE_ROLES == (Role.REGISTRAR,)


def test_api_response_shapes_exclude_sensitive_information():
    now = datetime.now(timezone.utc)
    parcel = Parcel(
        parcel_id="parcel-1",
        cadastral_number="CAD-1",
        location="Ward 1",
        area=Decimal("10"),
        area_unit=AreaUnit.HECTARES,
        status=ParcelStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    ownership = Ownership(
        ownership_id="ownership-1",
        parcel_id="parcel-1",
        owner_id="citizen-1",
        share=Decimal("100"),
        status=OwnershipStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    parcel_body = _parcel_response(parcel)
    ownership_body = _ownership_response(ownership)

    assert parcel_body["area"] == "10"
    assert ownership_body["share"] == "100"
    for body in (parcel_body, ownership_body):
        assert not any("password" in key or "hash" in key for key in body)
        assert not any("secret" in key for key in body)

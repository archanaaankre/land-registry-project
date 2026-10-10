from datetime import datetime, timezone
from decimal import Decimal
import secrets

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

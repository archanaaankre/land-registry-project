"""Registrar ownership creation API tests (real SQLite database)."""

import os
from decimal import Decimal

import pytest

from app import create_app, db
from app.auth.service import create_access_token, hash_password
from app.config import Config
from app.models import (
    AreaUnit,
    Parcel,
    ParcelStatus,
    Role,
    utc_now,
)
from app.persistence.repositories import (
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemyUserRepository,
)


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "ownership.db").replace("\\", "/")


def _prepare_app(database_url):
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-ownership-creation",
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with app.app_context():
        db.create_all()
    user_repository = SqlAlchemyUserRepository()
    parcel_repository = SqlAlchemyParcelRepository()
    ownership_repository = SqlAlchemyOwnershipRepository()
    app.config.update(
        AUTH_USER_REPOSITORY=user_repository,
        PARCEL_REPOSITORY=parcel_repository,
        OWNERSHIP_REPOSITORY=ownership_repository,
    )
    return app, user_repository, parcel_repository, ownership_repository


def _headers(app, user_id, role):
    token = create_access_token(user_id, role, app.config["JWT_SECRET_KEY"])
    return {"Authorization": "Bearer " + token}


def _seed(app, user_repository, parcel_repository):
    with app.app_context():
        citizen = user_repository.create_user(
            name="Asha Rao",
            email="asha@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.CITIZEN,
        )
        other_citizen = user_repository.create_user(
            name="Ben Rise",
            email="ben@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.CITIZEN,
        )
        registrar = user_repository.create_user(
            name="Reg Null",
            email="reg@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-1",
                cadastral_number="CAD-1",
                location="Ward 1",
                area=Decimal("2.5"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        return citizen, other_citizen, registrar


def _ownership_payload(ownership_id, owner_id, share=100, status="ACTIVE"):
    return {
        "ownership_id": ownership_id,
        "parcel_id": "parcel-1",
        "owner_id": owner_id,
        "share": share,
        "status": status,
    }


def test_registrar_can_record_ownership_for_existing_parcel(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    client = app.test_client()
    citizen, _other, registrar = _seed(app, user_repository, parcel_repository)
    headers = _headers(app, registrar.id, Role.REGISTRAR)

    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-1", citizen.id, share=100),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.get_json()["ownership"]
    assert body["ownership_id"] == "ownership-1"
    assert body["parcel_id"] == "parcel-1"
    assert body["owner_id"] == citizen.id
    assert Decimal(body["share"]) == Decimal("100")
    assert body["status"] == "ACTIVE"
    with app.app_context():
        assert ownership_repository.find_by_id("ownership-1") is not None


def test_registrar_rejects_missing_parcel_and_owner(tmp_path):
    app, user_repository, parcel_repository, _ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    client = app.test_client()
    citizen, _other, registrar = _seed(app, user_repository, parcel_repository)
    headers = _headers(app, registrar.id, Role.REGISTRAR)

    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-missing-parcel", citizen.id)
        | {"parcel_id": "parcel-does-not-exist"},
        headers=headers,
    )
    assert response.status_code == 404

    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-missing-owner", "user-nobody", share=50),
        headers=headers,
    )
    assert response.status_code == 404


def test_share_validation_and_duplicate_prevention(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    client = app.test_client()
    citizen, other_citizen, registrar = _seed(app, user_repository, parcel_repository)
    headers = _headers(app, registrar.id, Role.REGISTRAR)

    # Invalid share (> 100) is rejected as input.
    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-invalid-share", citizen.id, share=101),
        headers=headers,
    )
    assert response.status_code == 400

    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-first", citizen.id, share=60),
        headers=headers,
    )
    assert response.status_code == 201

    # Duplicate active ownership for the same owner on the same parcel.
    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-second", citizen.id, share=40),
        headers=headers,
    )
    assert response.status_code == 409

    # Share total for the parcel exceeds 100%.
    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-third", other_citizen.id, share=41),
        headers=headers,
    )
    assert response.status_code == 409

    with app.app_context():
        assert ownership_repository.find_by_id("ownership-invalid-share") is None
        assert ownership_repository.find_by_id("ownership-second") is None
        assert ownership_repository.find_by_id("ownership-third") is None
        assert ownership_repository.find_by_id("ownership-first") is not None


@pytest.mark.parametrize(
    "role",
    [Role.CITIZEN, Role.VERIFICATION_OFFICER, Role.ADMIN],
)
def test_non_registrar_cannot_create_ownership(tmp_path, role):
    app, user_repository, parcel_repository, _ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    client = app.test_client()
    citizen, _other, _registrar = _seed(app, user_repository, parcel_repository)
    headers = _headers(app, citizen.id, role)

    response = client.post(
        "/api/ownership",
        json=_ownership_payload("ownership-denied", citizen.id, share=10),
        headers=headers,
    )
    assert response.status_code == 403

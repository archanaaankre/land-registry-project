import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from app import create_app, db
from app.auth.service import hash_password
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
    TransferStatus,
    utc_now,
)
from app.persistence.repositories import (
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
)


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "land_registry.db").replace("\\", "/")


def _prepare_app(database_url):
    from app.config import Config

    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-persistence-only",
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with app.app_context():
        db.create_all()
    user_repository = SqlAlchemyUserRepository()
    parcel_repository = SqlAlchemyParcelRepository()
    ownership_repository = SqlAlchemyOwnershipRepository()
    transfer_repository = SqlAlchemyTransferRepository()
    app.config.update(
        AUTH_USER_REPOSITORY=user_repository,
        PARCEL_REPOSITORY=parcel_repository,
        OWNERSHIP_REPOSITORY=ownership_repository,
        TRANSFER_REPOSITORY=transfer_repository,
    )
    return app, user_repository, parcel_repository, ownership_repository, transfer_repository


def _json(response):
    return response.get_json()


def _registration_payload(email, name="Asha Rao"):
    return {
        "name": name,
        "email": email,
        "password": "a secure password",
        "role": "CITIZEN",
    }


def test_user_registration_persists_across_application_restart(tmp_path):
    database_url = _database_url(tmp_path)

    app, user_repository, *_ = _prepare_app(database_url)
    client = app.test_client()

    first = client.post("/api/auth/register", json=_registration_payload("asha@example.com"))
    assert first.status_code == 201
    user = _json(first)["user"]

    second_app, *_ = _prepare_app(database_url)
    second_client = second_app.test_client()
    login = second_client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "a secure password"},
    )
    assert login.status_code == 200
    assert _json(login)["user"]["id"] == user["id"]

    duplicate = second_client.post(
        "/api/auth/register", json=_registration_payload("asha@example.com")
    )
    assert duplicate.status_code == 400


def test_parcel_and_ownership_records_are_persisted_and_protected(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, _ = _prepare_app(database_url)
    client = app.test_client()

    registration = client.post(
        "/api/auth/register", json=_registration_payload("citizen@example.com")
    )
    owner_id = _json(registration)["user"]["id"]
    token = registration.get_json()["access_token"]

    parcel = Parcel(
        parcel_id="parcel-persisted",
        cadastral_number="CAD-P",
        location="Ward 5",
        area=Decimal("12.5"),
        area_unit=AreaUnit.HECTARES,
        status=ParcelStatus.ACTIVE,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    ownership = Ownership(
        ownership_id="ownership-persisted",
        parcel_id="parcel-persisted",
        owner_id=owner_id,
        share=Decimal("100"),
        status=OwnershipStatus.ACTIVE,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    with app.app_context():
        parcel_repository.create_parcel(parcel)
        ownership_repository.create_ownership(ownership)

    listed = client.get("/api/parcels", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert [item["parcel_id"] for item in _json(listed)["items"]] == ["parcel-persisted"]

    details = client.get(
        "/api/parcels/parcel-persisted/ownership",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert details.status_code == 200
    assert _json(details)["items"][0]["owner_id"] == owner_id

    unauthenticated = client.get("/api/parcels")
    assert unauthenticated.status_code == 401


def test_transfer_workflow_persists_to_database(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, _ = _prepare_app(database_url)
    client = app.test_client()

    seller_registration = client.post(
        "/api/auth/register", json=_registration_payload("seller@example.com")
    )
    seller_id = _json(seller_registration)["user"]["id"]
    seller_token = _json(seller_registration)["access_token"]

    buyer_registration = client.post(
        "/api/auth/register",
        json=_registration_payload("buyer@example.com", "Buyer Rao"),
    )
    buyer_email = _json(buyer_registration)["user"]["email"]

    with app.app_context():
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-transfer",
                cadastral_number="CAD-T",
                location="Ward 9",
                area=Decimal("20"),
                area_unit=AreaUnit.SQ_METERS,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-transfer",
                parcel_id="parcel-transfer",
                owner_id=seller_id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

    with app.app_context():
        registrar = user_repository.create_user(
            name="Registrar One",
            email="registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
    registrar_token = _login(client, "registrar@example.com", "registrar password")

    created = client.post(
        "/api/transfers",
        json={"parcel_id": "parcel-transfer", "buyer_reference": buyer_email},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert created.status_code == 201
    created_body = _json(created)["transfer"]
    assert created_body["status"] == "SUBMITTED"

    pending = client.get(
        "/api/registrar/transfers",
        headers={"Authorization": f"Bearer {registrar_token}"},
    )
    assert pending.status_code == 200
    assert [_json(pending)["items"][0]["request_id"]] == [created_body["request_id"]]

    approved = client.post(
        "/api/registrar/transfers/{0}/approve".format(created_body["request_id"]),
        headers={"Authorization": f"Bearer {registrar_token}"},
    )
    assert approved.status_code == 200
    assert _json(approved)["transfer"]["status"] == "APPROVED"
    assert _json(approved)["transfer"]["blockchain_status"] == "UNAVAILABLE"

    detailed = client.get(
        "/api/transfers/{0}".format(created_body["request_id"]),
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert detailed.status_code == 200
    history = _json(detailed)["history"]
    event_types = [event["event_type"] for event in history]
    assert "TRANSFER_SUBMITTED" in event_types
    assert "TRANSFER_APPROVED" in event_types


def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return _json(response)["access_token"]

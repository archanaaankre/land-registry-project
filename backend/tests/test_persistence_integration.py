import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from app import create_app, db
from app.auth.errors import InvalidInputError, ResourceConflictError
from app.auth.service import hash_password
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
    TransferAuditEvent,
    TransferRequest,
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


def test_active_transfer_constraint_handles_duplicate_requests_atomically(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, _, transfer_repository = _prepare_app(database_url)
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="seller-constraint@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-constraint",
                cadastral_number="CAD-C",
                location="Ward C",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )

        first = TransferRequest(
            request_id="transfer-constraint-1",
            parcel_id="parcel-constraint",
            seller_id=seller.id,
            buyer_reference="buyer-one@example.com",
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        first_event = TransferAuditEvent(
            event_id="event-constraint-1",
            request_id=first.request_id,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        transfer_repository.create_request_with_audit(first, first_event)

        second = TransferRequest(
            request_id="transfer-constraint-2",
            parcel_id="parcel-constraint",
            seller_id=seller.id,
            buyer_reference="buyer-two@example.com",
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        second_event = TransferAuditEvent(
            event_id="event-constraint-2",
            request_id=second.request_id,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        with pytest.raises(ResourceConflictError):
            transfer_repository.create_request_with_audit(second, second_event)

        assert transfer_repository.find_by_id(second.request_id) is None
        assert len(transfer_repository.list_audit_events(first.request_id)) == 1
        assert transfer_repository.list_audit_events(second.request_id) == []


def test_transfer_request_is_rolled_back_when_audit_event_cannot_be_saved(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, _, transfer_repository = _prepare_app(database_url)
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="seller-rollback@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-rollback",
                cadastral_number="CAD-R",
                location="Ward R",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        original_request = TransferRequest(
            request_id="transfer-rollback-1",
            parcel_id="parcel-rollback",
            seller_id=seller.id,
            buyer_reference="buyer-one@example.com",
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        duplicate_event = TransferAuditEvent(
            event_id="event-duplicate",
            request_id=original_request.request_id,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        transfer_repository.create_request_with_audit(original_request, duplicate_event)

        rejected_request = TransferRequest(
            request_id="transfer-rollback-2",
            parcel_id="parcel-rollback",
            seller_id=seller.id,
            buyer_reference="buyer-two@example.com",
            status=TransferStatus.REJECTED,
            created_at=now,
            updated_at=now,
        )
        rejected_event = TransferAuditEvent(
            event_id="event-duplicate",
            request_id=rejected_request.request_id,
            event_type="TRANSFER_REJECTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.REJECTED,
            reason="Rejected",
            created_at=now,
        )
        with pytest.raises(InvalidInputError):
            transfer_repository.create_request_with_audit(rejected_request, rejected_event)

        assert transfer_repository.find_by_id(rejected_request.request_id) is None
        assert transfer_repository.list_audit_events(rejected_request.request_id) == []


def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return _json(response)["access_token"]

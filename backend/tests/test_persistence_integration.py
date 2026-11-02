import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from app import create_app, db
from app.auth.errors import InvalidInputError, ResourceConflictError
from app.auth.service import create_access_token, hash_password
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


def test_registrar_creates_parcels_and_ownership_through_api(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, _, _, _ = _prepare_app(database_url)
    client = app.test_client()

    with app.app_context():
        registrar = user_repository.create_user(
            name="Registrar",
            email="registry-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
    citizen_registration = client.post(
        "/api/auth/register",
        json=_registration_payload("registry-owner@example.com"),
    )
    assert citizen_registration.status_code == 201
    owner_id = _json(citizen_registration)["user"]["id"]
    registrar_token = _login(
        client, registrar.email, "registrar password"
    )
    headers = {"Authorization": f"Bearer {registrar_token}"}

    parcel_payload = {
        "parcel_id": "parcel-api-created",
        "cadastral_number": "CAD-API",
        "location": "Ward API",
        "area": 12.5,
        "area_unit": "HECTARES",
        "status": "ACTIVE",
    }
    created_parcel = client.post(
        "/api/parcels", json=parcel_payload, headers=headers
    )
    assert created_parcel.status_code == 201
    assert _json(created_parcel)["parcel"]["parcel_id"] == "parcel-api-created"

    ownership_payload = {
        "ownership_id": "ownership-api-created",
        "parcel_id": "parcel-api-created",
        "owner_id": owner_id,
        "share": 100,
        "status": "ACTIVE",
    }
    created_ownership = client.post(
        "/api/ownership", json=ownership_payload, headers=headers
    )
    assert created_ownership.status_code == 201
    assert _json(created_ownership)["ownership"]["owner_id"] == owner_id

    duplicate_parcel = client.post(
        "/api/parcels", json=parcel_payload, headers=headers
    )
    duplicate_ownership = client.post(
        "/api/ownership", json=ownership_payload, headers=headers
    )
    assert duplicate_parcel.status_code == 400
    assert duplicate_ownership.status_code == 409
    assert _json(duplicate_parcel)["error"]["code"] == "invalid_input"
    assert _json(duplicate_ownership)["error"]["code"] == "conflict"

    inactive_payload = {
        "ownership_id": "ownership-api-history",
        "parcel_id": "parcel-api-created",
        "owner_id": owner_id,
        "share": 100,
        "status": "INACTIVE",
    }
    created_inactive = client.post(
        "/api/ownership", json=inactive_payload, headers=headers
    )
    assert created_inactive.status_code == 201

    current = client.get(
        "/api/parcels/parcel-api-created/ownership/current", headers=headers
    )
    history = client.get(
        "/api/parcels/parcel-api-created/ownership/history", headers=headers
    )
    assert [item["ownership_id"] for item in _json(current)["items"]] == [
        "ownership-api-created"
    ]
    assert [item["ownership_id"] for item in _json(history)["items"]] == [
        "ownership-api-history"
    ]


def test_ownership_share_constraints_are_atomic_and_parcel_scoped(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, _ = _prepare_app(
        database_url
    )
    client = app.test_client()
    owner_tokens = []
    with app.app_context():
        for index in range(3):
            user = user_repository.create_user(
                name=f"Owner {index}",
                email=f"owner-{index}@example.com",
                password_hash=hash_password("owner password"),
                role=Role.CITIZEN,
            )
            owner_tokens.append(user.id)
        for index in range(3):
            parcel_repository.create_parcel(
                Parcel(
                    parcel_id=f"ownership-parcel-{index}",
                    cadastral_number=f"OWN-CAD-{index}",
                    location="Ward ownership",
                    area=Decimal("10"),
                    area_unit=AreaUnit.HECTARES,
                    status=ParcelStatus.ACTIVE,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )

        registrar = user_repository.create_user(
            name="Ownership Registrar",
            email="ownership-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
    headers = {
        "Authorization": "Bearer "
        + create_access_token(
            registrar.id, Role.REGISTRAR, app.config["JWT_SECRET_KEY"]
        )
    }

    def create_record(ownership_id, parcel_id, owner_id, share):
        return client.post(
            "/api/ownership",
            headers=headers,
            json={
                "ownership_id": ownership_id,
                "parcel_id": parcel_id,
                "owner_id": owner_id,
                "share": share,
                "status": "ACTIVE",
            },
        )

    assert create_record(
        "ownership-share-1", "ownership-parcel-0", owner_tokens[0], 33.333333
    ).status_code == 201
    assert create_record(
        "ownership-share-2", "ownership-parcel-0", owner_tokens[1], 66.666667
    ).status_code == 201

    overallocated = create_record(
        "ownership-share-3", "ownership-parcel-0", owner_tokens[2], 0.000001
    )
    separate_parcel = create_record(
        "ownership-share-4", "ownership-parcel-1", owner_tokens[0], 100
    )
    invalid_owner = create_record(
        "ownership-share-5",
        "ownership-parcel-2",
        "missing-citizen",
        0.000001,
    )
    assert overallocated.status_code == 409
    assert separate_parcel.status_code == 201
    assert invalid_owner.status_code == 404

    with app.app_context():
        assert [
            record.ownership_id
            for record in ownership_repository.list_for_parcel("ownership-parcel-0")
        ] == ["ownership-share-1", "ownership-share-2"]


def test_ownership_repository_rejects_non_citizen_owner_and_rolls_back(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, _ = _prepare_app(
        database_url
    )
    with app.app_context():
        registrar = user_repository.create_user(
            name="Not an Owner",
            email="not-owner@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="ownership-role-parcel",
                cadastral_number="OWN-ROLE-CAD",
                location="Ward ownership",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

        with pytest.raises(InvalidInputError, match="citizen"):
            ownership_repository.create_ownership(
                Ownership(
                    ownership_id="ownership-invalid-role",
                    parcel_id="ownership-role-parcel",
                    owner_id=registrar.id,
                    share=Decimal("100"),
                    status=OwnershipStatus.ACTIVE,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        assert ownership_repository.list_for_parcel("ownership-role-parcel") == []


def test_ownership_repository_rechecks_shares_and_rolls_back(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, _ = _prepare_app(
        database_url
    )
    with app.app_context():
        owners = [
            user_repository.create_user(
                name=f"Owner {index}",
                email=f"atomic-owner-{index}@example.com",
                password_hash=hash_password("owner password"),
                role=Role.CITIZEN,
            )
            for index in range(2)
        ]
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="ownership-atomic-parcel",
                cadastral_number="OWN-ATOMIC-CAD",
                location="Ward ownership",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-atomic-existing",
                parcel_id="ownership-atomic-parcel",
                owner_id=owners[0].id,
                share=Decimal("70"),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

        with pytest.raises(ResourceConflictError, match="cannot exceed 100%"):
            ownership_repository.create_ownership(
                Ownership(
                    ownership_id="ownership-atomic-overflow",
                    parcel_id="ownership-atomic-parcel",
                    owner_id=owners[1].id,
                    share=Decimal("31"),
                    status=OwnershipStatus.ACTIVE,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        with pytest.raises(ResourceConflictError, match="already has an active"):
            ownership_repository.create_ownership(
                Ownership(
                    ownership_id="ownership-atomic-duplicate",
                    parcel_id="ownership-atomic-parcel",
                    owner_id=owners[0].id,
                    share=Decimal("20"),
                    status=OwnershipStatus.ACTIVE,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )

        records = ownership_repository.list_for_parcel(
            "ownership-atomic-parcel"
        )
        assert [(record.ownership_id, record.share) for record in records] == [
            ("ownership-atomic-existing", Decimal("70.000000"))
        ]


def test_transfer_workflow_persists_to_database(tmp_path):
    database_url = _database_url(tmp_path)
    (
        app,
        user_repository,
        parcel_repository,
        ownership_repository,
        transfer_repository,
    ) = _prepare_app(database_url)
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
    buyer_id = _json(buyer_registration)["user"]["id"]

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

    cancelled = client.post(
        "/api/transfers/{0}/cancel".format(created_body["request_id"]),
        json={"reason": "Buyer withdrew"},
        headers={"Authorization": "Bearer " + seller_token},
    )
    assert cancelled.status_code == 200
    assert _json(cancelled)["transfer"]["status"] == "CANCELLED"
    with app.app_context():
        transfer_events = transfer_repository.list_audit_events(
            created_body["request_id"]
        )
        current_ownership = ownership_repository.list_for_parcel("parcel-transfer")
    assert [event.event_type for event in transfer_events][-1] == "TRANSFER_CANCELLED"
    assert len(current_ownership) == 1
    assert current_ownership[0].owner_id == seller_id

    resubmitted = client.post(
        "/api/transfers",
        json={"parcel_id": "parcel-transfer", "buyer_reference": buyer_id},
        headers={"Authorization": "Bearer " + seller_token},
    )
    assert resubmitted.status_code == 201
    assert _json(resubmitted)["transfer"]["buyer_reference"] == buyer_id
    buyer_transfers = client.get(
        "/api/transfers",
        headers={
            "Authorization": "Bearer "
            + create_access_token(
                buyer_id, Role.CITIZEN, app.config["JWT_SECRET_KEY"]
            )
        },
    )
    assert buyer_transfers.status_code == 200
    assert {
        transfer["request_id"] for transfer in _json(buyer_transfers)["items"]
    } == {
        created_body["request_id"],
        _json(resubmitted)["transfer"]["request_id"],
    }

    with app.app_context():
        current_ownership = ownership_repository.list_for_parcel("parcel-transfer")
    assert len(current_ownership) == 1
    assert current_ownership[0].owner_id == seller_id
    assert current_ownership[0].share == Decimal("100.000000")


def test_transfer_submission_revalidates_parcel_owner_and_buyer_in_database(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, transfer_repository = (
        _prepare_app(database_url)
    )
    client = app.test_client()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="state-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        coowner = user_repository.create_user(
            name="Co-owner",
            email="state-coowner@example.com",
            password_hash=hash_password("coowner password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="state-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        registrar_buyer = user_repository.create_user(
            name="Registrar",
            email="state-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        for parcel_id, status in (
            ("parcel-disputed-transfer", ParcelStatus.DISPUTED),
            ("parcel-shared-transfer", ParcelStatus.ACTIVE),
            ("parcel-role-transfer", ParcelStatus.ACTIVE),
        ):
            parcel_repository.create_parcel(
                Parcel(
                    parcel_id=parcel_id,
                    cadastral_number=f"CAD-{parcel_id}",
                    location="Ward transfer",
                    area=Decimal("10"),
                    area_unit=AreaUnit.HECTARES,
                    status=status,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-disputed-transfer",
                parcel_id="parcel-disputed-transfer",
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        for ownership_id, owner_id in (
            ("ownership-shared-seller", seller.id),
            ("ownership-shared-coowner", coowner.id),
        ):
            ownership_repository.create_ownership(
                Ownership(
                    ownership_id=ownership_id,
                    parcel_id="parcel-shared-transfer",
                    owner_id=owner_id,
                    share=Decimal("50"),
                    status=OwnershipStatus.ACTIVE,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-role-transfer",
                parcel_id="parcel-role-transfer",
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

    seller_headers = {
        "Authorization": "Bearer "
        + create_access_token(seller.id, Role.CITIZEN, app.config["JWT_SECRET_KEY"])
    }

    def submit(parcel_id, buyer_reference):
        return client.post(
            "/api/transfers",
            json={
                "parcel_id": parcel_id,
                "buyer_reference": buyer_reference,
            },
            headers=seller_headers,
        )

    assert submit("parcel-disputed-transfer", buyer.email).status_code == 409
    assert submit("parcel-shared-transfer", buyer.email).status_code == 409
    non_citizen_buyer = submit("parcel-role-transfer", registrar_buyer.id)
    assert non_citizen_buyer.status_code == 400
    assert _json(non_citizen_buyer)["error"]["field"] == "buyer_reference"

    with app.app_context():
        assert transfer_repository.list_all() == []
        assert all(
            transfer_repository.list_audit_events(request_id) == []
            for request_id in (
                "transfer-disputed-transfer",
                "transfer-shared-transfer",
                "transfer-role-transfer",
            )
        )


def test_transfer_status_and_audit_update_roll_back_together_on_failure(tmp_path):
    database_url = _database_url(tmp_path)
    app, user_repository, parcel_repository, ownership_repository, transfer_repository = (
        _prepare_app(database_url)
    )
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="rollback-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="rollback-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        registrar = user_repository.create_user(
            name="Registrar",
            email="rollback-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-decision-rollback",
                cadastral_number="CAD-DECISION-ROLLBACK",
                location="Ward transfer",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-decision-rollback",
                parcel_id="parcel-decision-rollback",
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        transfer = TransferRequest(
            request_id="transfer-decision-rollback",
            parcel_id="parcel-decision-rollback",
            seller_id=seller.id,
            buyer_reference=buyer.email,
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        duplicate_event = TransferAuditEvent(
            event_id="event-decision-rollback",
            request_id=transfer.request_id,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        transfer_repository.create_request_with_audit(transfer, duplicate_event)

        rejected = transfer.__class__(
            **{
                **transfer.__dict__,
                "status": TransferStatus.REJECTED,
                "reviewer_id": registrar.id,
                "reviewed_at": now,
                "review_reason": "Rejected",
                "updated_at": now,
            }
        )
        conflicting_event = TransferAuditEvent(
            event_id=duplicate_event.event_id,
            request_id=transfer.request_id,
            event_type="TRANSFER_REJECTED",
            actor_id=registrar.id,
            actor_role=Role.REGISTRAR,
            from_status=TransferStatus.SUBMITTED,
            to_status=TransferStatus.REJECTED,
            reason="Rejected",
            created_at=now,
        )
        with pytest.raises(InvalidInputError):
            transfer_repository.save_request_with_audit(
                rejected,
                TransferStatus.SUBMITTED,
                conflicting_event,
            )

        stored = transfer_repository.find_by_id(transfer.request_id)
        events = transfer_repository.list_audit_events(transfer.request_id)
        assert stored.status is TransferStatus.SUBMITTED
        assert stored.reviewer_id is None
        assert [event.event_id for event in events] == [duplicate_event.event_id]


def test_active_transfer_constraint_handles_duplicate_requests_atomically(tmp_path):
    database_url = _database_url(tmp_path)
    (
        app,
        user_repository,
        parcel_repository,
        ownership_repository,
        transfer_repository,
    ) = _prepare_app(database_url)
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="seller-constraint@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="buyer-one@example.com",
            password_hash=hash_password("buyer password"),
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
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-constraint",
                parcel_id="parcel-constraint",
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )

        first = TransferRequest(
            request_id="transfer-constraint-1",
            parcel_id="parcel-constraint",
            seller_id=seller.id,
            buyer_reference=buyer.email,
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
            buyer_reference=buyer.email,
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
    (
        app,
        user_repository,
        parcel_repository,
        ownership_repository,
        transfer_repository,
    ) = _prepare_app(database_url)
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="seller-rollback@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="buyer-one@example.com",
            password_hash=hash_password("buyer password"),
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
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-rollback",
                parcel_id="parcel-rollback",
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        original_request = TransferRequest(
            request_id="transfer-rollback-1",
            parcel_id="parcel-rollback",
            seller_id=seller.id,
            buyer_reference=buyer.email,
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
            buyer_reference=buyer.email,
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

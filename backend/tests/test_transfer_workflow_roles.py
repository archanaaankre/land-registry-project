"""Four-role transfer workflow authorization and finalization safety.

Disposable SQLite only. No shared database is contacted, no migrations run,
and no finalization route or callback is introduced.
"""

import os
import secrets
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import AuthorizationError, ResourceConflictError
from app.auth.service import create_access_token, hash_password
from app.config import Config
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
from app.transfers.authorization import TRANSFER_FINALIZE_ROLES
from app.transfers.blockchain import UnavailableBlockchainGateway
from app.transfers.services import TransferService

PARCEL_ID = "parcel-1"


@pytest.fixture
def seed(tmp_path):
    database_url = "sqlite:///" + str(tmp_path / "transfer_roles.db").replace("\\", "/")
    previous_url = os.environ.get("DATABASE_URL")
    previous_config = Config.SQLALCHEMY_DATABASE_URI
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    try:
        application = create_app()
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        Config.SQLALCHEMY_DATABASE_URI = previous_config

    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    user_repository = SqlAlchemyUserRepository()
    parcel_repository = SqlAlchemyParcelRepository()
    ownership_repository = SqlAlchemyOwnershipRepository()
    transfer_repository = SqlAlchemyTransferRepository()
    gateway = UnavailableBlockchainGateway()
    application.config.update(
        AUTH_USER_REPOSITORY=user_repository,
        PARCEL_REPOSITORY=parcel_repository,
        OWNERSHIP_REPOSITORY=ownership_repository,
        TRANSFER_REPOSITORY=transfer_repository,
        BLOCKCHAIN_GATEWAY=gateway,
    )

    with application.app_context():
        db.create_all()
        users = {}
        for role in Role:
            users[role] = user_repository.create_user(
                name=f"Test {role.value}",
                email=f"{role.value.lower()}@example.com",
                password_hash=hash_password("a valid test password"),
                role=role,
            )
        seller = users[Role.CITIZEN]
        buyer = user_repository.create_user(
            name="Buyer",
            email="buyer@example.com",
            password_hash=hash_password("a valid test password"),
            role=Role.CITIZEN,
        )
        stranger = user_repository.create_user(
            name="Stranger",
            email="stranger@example.com",
            password_hash=hash_password("a valid test password"),
            role=Role.CITIZEN,
        )
        now = utc_now()
        parcel_repository.create_parcel(
            Parcel(
                parcel_id=PARCEL_ID,
                cadastral_number="CAD-TRANSFER-1",
                location="Ward 1",
                area=Decimal("10"),
                area_unit=AreaUnit.SQ_METERS,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                created_by=users[Role.REGISTRAR].id,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-1",
                parcel_id=PARCEL_ID,
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        service = TransferService(
            transfer_repository,
            parcel_repository,
            ownership_repository,
            user_repository,
            blockchain_gateway=gateway,
        )
        transfer = service.submit_transfer(
            seller.id,
            {"parcel_id": PARCEL_ID, "buyer_reference": buyer.id},
            actor_role=Role.CITIZEN,
        )

    yield SimpleNamespace(
        app=application,
        client=application.test_client(),
        users=users,
        seller=seller,
        buyer=buyer,
        stranger=stranger,
        user_repository=user_repository,
        parcel_repository=parcel_repository,
        ownership_repository=ownership_repository,
        transfer_repository=transfer_repository,
        transfer=transfer,
        gateway=gateway,
    )
    with application.app_context():
        db.session.remove()
        db.drop_all()


def headers(seed, role, user=None):
    actor = user or seed.users[role]
    token = create_access_token(actor.id, role, seed.app.config["JWT_SECRET_KEY"])
    return {"Authorization": "Bearer " + token}


def service(seed):
    return TransferService(
        seed.transfer_repository,
        seed.parcel_repository,
        seed.ownership_repository,
        seed.user_repository,
        blockchain_gateway=seed.gateway,
    )


def active_owner_ids(seed):
    with seed.app.app_context():
        return [
            record.owner_id
            for record in seed.ownership_repository.list_for_parcel(PARCEL_ID)
            if record.status is OwnershipStatus.ACTIVE
        ]


# --- Read access for all four roles ---------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_list_transfers(seed, role):
    response = seed.client.get("/api/transfers", headers=headers(seed, role))
    assert response.status_code == 200
    assert [item["request_id"] for item in response.get_json()["items"]] == [
        seed.transfer.request_id
    ]


def test_only_registrar_can_list_review_queue(seed):
    registrar_response = seed.client.get(
        "/api/registrar/transfers",
        headers=headers(seed, Role.REGISTRAR),
    )
    assert registrar_response.status_code == 200
    assert [item["request_id"] for item in registrar_response.get_json()["items"]] == [
        seed.transfer.request_id
    ]

    for role in (Role.CITIZEN, Role.VERIFICATION_OFFICER, Role.ADMIN):
        response = seed.client.get(
            "/api/registrar/transfers",
            headers=headers(seed, role),
        )
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_read_transfer_detail(seed, role):
    response = seed.client.get(
        f"/api/transfers/{seed.transfer.request_id}", headers=headers(seed, role)
    )
    assert response.status_code == 200
    assert response.get_json()["transfer"]["request_id"] == seed.transfer.request_id
    assert response.get_json()["history"][0]["event_type"] == "TRANSFER_SUBMITTED"


def test_unrelated_citizen_does_not_see_another_users_transfer(seed):
    response = seed.client.get(
        "/api/transfers", headers=headers(seed, Role.CITIZEN, seed.stranger)
    )
    assert response.status_code == 200
    assert response.get_json()["items"] == []
    detail = seed.client.get(
        f"/api/transfers/{seed.transfer.request_id}",
        headers=headers(seed, Role.CITIZEN, seed.stranger),
    )
    assert detail.status_code == 403


# --- Verification Officer cannot approve or reject ------------------------


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_verification_officer_cannot_approve_or_reject(seed, action):
    response = seed.client.post(
        f"/api/registrar/transfers/{seed.transfer.request_id}/{action}",
        headers=headers(seed, Role.VERIFICATION_OFFICER),
        json={"reason": "document check"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
    with seed.app.app_context():
        stored = seed.transfer_repository.find_by_id(seed.transfer.request_id)
        assert stored.status is TransferStatus.SUBMITTED


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_service_rejects_non_registrar_decisions(seed, action):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        method = getattr(service(seed), f"{action}_request")
        if action == "approve":
            method(
                seed.users[Role.VERIFICATION_OFFICER].id,
                Role.VERIFICATION_OFFICER,
                seed.transfer.request_id,
            )
        else:
            method(
                seed.users[Role.ADMIN].id,
                Role.ADMIN,
                seed.transfer.request_id,
                "not allowed",
            )


# --- Registrar decisions and ownership safety -----------------------------


def test_registrar_can_approve_without_changing_ownership(seed):
    response = seed.client.post(
        f"/api/registrar/transfers/{seed.transfer.request_id}/approve",
        headers=headers(seed, Role.REGISTRAR),
        json={"reason": "documents verified"},
    )
    assert response.status_code == 200
    assert response.get_json()["transfer"]["status"] == "APPROVED"
    assert response.get_json()["transfer"]["blockchain_status"] == "UNAVAILABLE"
    assert active_owner_ids(seed) == [seed.seller.id]


def test_registrar_can_reject_with_reason(seed):
    response = seed.client.post(
        f"/api/registrar/transfers/{seed.transfer.request_id}/reject",
        headers=headers(seed, Role.REGISTRAR),
        json={"reason": "documents out of order"},
    )
    assert response.status_code == 200
    assert response.get_json()["transfer"]["status"] == "REJECTED"
    assert active_owner_ids(seed) == [seed.seller.id]


# --- Cancellation follows existing rules ----------------------------------


def test_seller_can_cancel_and_others_cannot(seed):
    stranger_cancel = seed.client.post(
        f"/api/transfers/{seed.transfer.request_id}/cancel",
        headers=headers(seed, Role.CITIZEN, seed.stranger),
        json={"reason": "not mine"},
    )
    officer_cancel = seed.client.post(
        f"/api/transfers/{seed.transfer.request_id}/cancel",
        headers=headers(seed, Role.VERIFICATION_OFFICER),
        json={"reason": "not mine"},
    )
    seller_cancel = seed.client.post(
        f"/api/transfers/{seed.transfer.request_id}/cancel",
        headers=headers(seed, Role.CITIZEN),
        json={"reason": "changed mind"},
    )
    assert stranger_cancel.status_code == 403
    assert officer_cancel.status_code == 403
    assert seller_cancel.status_code == 200
    assert seller_cancel.get_json()["transfer"]["status"] == "CANCELLED"
    assert active_owner_ids(seed) == [seed.seller.id]


def test_seller_can_cancel_approved_transfer_while_blockchain_unavailable(seed):
    seed.client.post(
        f"/api/registrar/transfers/{seed.transfer.request_id}/approve",
        headers=headers(seed, Role.REGISTRAR),
        json={"reason": "approved"},
    )
    response = seed.client.post(
        f"/api/transfers/{seed.transfer.request_id}/cancel",
        headers=headers(seed, Role.CITIZEN),
        json={"reason": "withdrawn"},
    )
    assert response.status_code == 200
    assert response.get_json()["transfer"]["status"] == "CANCELLED"
    assert active_owner_ids(seed) == [seed.seller.id]


def test_service_rejects_non_citizen_cancellation(seed):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).cancel_request(
            seed.users[Role.REGISTRAR].id,
            Role.REGISTRAR,
            seed.transfer.request_id,
            "not the seller",
        )


# --- Finalization remains disabled and client-unreachable -----------------


def test_no_finalization_route_exists(seed):
    paths = {rule.rule for rule in seed.app.url_map.iter_rules()}
    assert not any("finalize" in path.lower() for path in paths)
    assert not any(path.lower().endswith("/confirm") for path in paths)
    for path in (
        f"/api/registrar/transfers/{seed.transfer.request_id}/finalize",
        f"/api/transfers/{seed.transfer.request_id}/confirm",
    ):
        response = seed.client.post(
            path,
            headers=headers(seed, Role.REGISTRAR),
            json={"blockchain_status": "CONFIRMED", "blockchain_tx_id": "fake-tx"},
        )
        assert response.status_code == 404


def test_finalization_roles_unchanged_and_no_client_confirmation(seed):
    assert set(TRANSFER_FINALIZE_ROLES) == {Role.REGISTRAR, Role.ADMIN}
    assert Role.CITIZEN not in TRANSFER_FINALIZE_ROLES
    assert Role.VERIFICATION_OFFICER not in TRANSFER_FINALIZE_ROLES
    with seed.app.app_context(), pytest.raises(ResourceConflictError):
        service(seed).finalize_transfer(
            seed.users[Role.REGISTRAR].id,
            Role.REGISTRAR,
            seed.transfer.request_id,
        )
    assert active_owner_ids(seed) == [seed.seller.id]
    with seed.app.app_context():
        stored = seed.transfer_repository.find_by_id(seed.transfer.request_id)
        assert stored.status is TransferStatus.SUBMITTED


def test_verification_officer_can_view_registry_records(seed):
    parcels = seed.client.get("/api/parcels", headers=headers(seed, Role.VERIFICATION_OFFICER))
    ownership = seed.client.get(
        f"/api/parcels/{PARCEL_ID}/ownership",
        headers=headers(seed, Role.VERIFICATION_OFFICER),
    )
    assert parcels.status_code == 200
    assert ownership.status_code == 200
    assert ownership.get_json()["items"][0]["owner_id"] == seed.seller.id

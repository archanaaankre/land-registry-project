"""Stable (canonical) buyer identity in transfer management.

A transfer resolves its buyer once at submission and persists the canonical
user ID on the record. Access checks, review validation, and ownership
finalization then use that canonical ID instead of re-resolving an email
address, so buyer access and finalization survive email changes. Legacy
records without a canonical ID keep the reference-based fallback and are
never silently reassigned to another user.
"""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import ResourceConflictError, ResourceNotFoundError
from app.auth.service import create_access_token, hash_password
from app.models import (
    AreaUnit,
    BlockchainSubmissionStatus,
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
from app.persistence.models import UserModel
from app.persistence.repositories import (
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
)
from app.registry.services import OwnershipService
from app.transfers.blockchain import BlockchainConfirmation, BlockchainSubmission
from app.transfers.services import TransferService

PARCEL_ID = "parcel-buyer-id"
REQUEST_ID_LEGACY = "transfer-legacy"
TX_ID = "0xbuyer-id-tx"


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "buyer_identity.db").replace("\\", "/")


def _prepare_app(database_url):
    from app.config import Config

    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-buyer-identity",
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


class StubBlockchainGateway:
    """Test double standing in for Person 1's integration gateway."""

    def __init__(self, *, tx_id=TX_ID, confirmation=None):
        self.tx_id = tx_id
        self.confirmation = confirmation

    def submit(self, request):
        return BlockchainSubmission(
            request_id=request.request_id,
            status=BlockchainSubmissionStatus.SUBMITTED,
            tx_id=self.tx_id,
        )

    def verify_confirmation(self, request_id):
        return self.confirmation


def _confirmation(request_id, parcel_id, tx_id=TX_ID):
    return BlockchainConfirmation(
        request_id=request_id,
        parcel_id=parcel_id,
        tx_id=tx_id,
        status=BlockchainSubmissionStatus.CONFIRMED,
        verified=True,
        confirmed_at=utc_now(),
    )


def _seed(app):
    user_repository = app.config["AUTH_USER_REPOSITORY"]
    parcel_repository = app.config["PARCEL_REPOSITORY"]
    ownership_repository = app.config["OWNERSHIP_REPOSITORY"]
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="id-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="id-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        stranger = user_repository.create_user(
            name="Stranger",
            email="id-stranger@example.com",
            password_hash=hash_password("stranger password"),
            role=Role.CITIZEN,
        )
        registrar = user_repository.create_user(
            name="Registrar",
            email="id-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id=PARCEL_ID,
                cadastral_number="CAD-ID",
                location="Ward Identity",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-id-seller",
                parcel_id=PARCEL_ID,
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    return SimpleNamespace(
        app=app,
        seller=seller,
        buyer=buyer,
        stranger=stranger,
        registrar=registrar,
        parcel_id=PARCEL_ID,
        user_repository=user_repository,
        parcel_repository=parcel_repository,
        ownership_repository=ownership_repository,
        transfer_repository=app.config["TRANSFER_REPOSITORY"],
    )


@pytest.fixture
def seed(tmp_path):
    app, *_ = _prepare_app(_database_url(tmp_path))
    return _seed(app)


def _headers(seed, user_id, role=Role.CITIZEN):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id, role, seed.app.config["JWT_SECRET_KEY"]
        )
    }


def _submit(seed, buyer_reference):
    client = seed.app.test_client()
    return client.post(
        "/api/transfers",
        headers=_headers(seed, seed.seller.id),
        json={"parcel_id": seed.parcel_id, "buyer_reference": buyer_reference},
    )


def _approve_http(seed, request_id):
    client = seed.app.test_client()
    return client.post(
        f"/api/registrar/transfers/{request_id}/approve",
        headers=_headers(seed, seed.registrar.id, Role.REGISTRAR),
    )


def _service(seed, gateway):
    return TransferService(
        seed.transfer_repository,
        seed.parcel_repository,
        seed.ownership_repository,
        seed.user_repository,
        blockchain_gateway=gateway,
    )


def _active_owner_ids(seed):
    with seed.app.app_context():
        records = seed.ownership_repository.list_for_parcel(seed.parcel_id)
    return [
        record.owner_id
        for record in records
        if record.status == OwnershipStatus.ACTIVE
    ]


# 1. Transfer submitted using buyer email.


def test_transfer_submitted_with_buyer_email(seed):
    response = _submit(seed, seed.buyer.email)

    assert response.status_code == 201
    body = response.get_json()["transfer"]
    assert body["status"] == "SUBMITTED"
    assert body["buyer_reference"] == seed.buyer.email
    assert body["buyer_id"] == seed.buyer.id


# 2. Transfer submitted using buyer ID.


def test_transfer_submitted_with_buyer_id(seed):
    response = _submit(seed, seed.buyer.id)

    assert response.status_code == 201
    body = response.get_json()["transfer"]
    assert body["buyer_reference"] == seed.buyer.id
    assert body["buyer_id"] == seed.buyer.id


# 3. Nonexistent buyer rejected.


def test_nonexistent_buyer_is_rejected(seed):
    response = _submit(seed, "ghost-buyer@example.com")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"
    with seed.app.app_context():
        assert seed.transfer_repository.list_all() == []


# 4. Non-citizen buyer rejected.


def test_non_citizen_buyer_is_rejected(seed):
    response = _submit(seed, seed.registrar.id)

    assert response.status_code == 400
    body = response.get_json()["error"]
    assert body["code"] == "invalid_input"
    assert body["field"] == "buyer_reference"
    with seed.app.app_context():
        assert seed.transfer_repository.list_all() == []


# 5. Seller cannot select themselves.


@pytest.mark.parametrize("form", ["id", "email"])
def test_seller_cannot_select_themselves(seed, form):
    reference = seed.seller.id if form == "id" else seed.seller.email

    response = _submit(seed, reference)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"
    with seed.app.app_context():
        assert seed.transfer_repository.list_all() == []


# 6. Canonical buyer ID is persisted and buyer_reference retained.


def test_canonical_buyer_id_is_persisted_and_reference_retained(seed):
    created = _submit(seed, seed.buyer.email)
    assert created.status_code == 201
    request_id = created.get_json()["transfer"]["request_id"]

    detail = seed.app.test_client().get(
        f"/api/transfers/{request_id}",
        headers=_headers(seed, seed.seller.id),
    )
    assert detail.status_code == 200
    body = detail.get_json()["transfer"]
    # The canonical ID round-trips through the database (not just the echo of
    # the submission response), and the original reference is retained.
    assert body["buyer_id"] == seed.buyer.id
    assert body["buyer_reference"] == seed.buyer.email

    # Approval rewrites the record; the canonical identity must survive it.
    assert _approve_http(seed, request_id).status_code == 200
    with seed.app.app_context():
        stored = seed.transfer_repository.find_by_id(request_id)
    assert stored.buyer_id == seed.buyer.id
    assert stored.buyer_reference == seed.buyer.email
    assert stored.status is TransferStatus.APPROVED


# 7. Buyer can access their transfer.


def test_buyer_can_access_their_transfer(seed):
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]
    client = seed.app.test_client()

    detail = client.get(
        f"/api/transfers/{request_id}", headers=_headers(seed, seed.buyer.id)
    )
    listed = client.get(
        "/api/transfers", headers=_headers(seed, seed.buyer.id)
    )

    assert detail.status_code == 200
    assert detail.get_json()["transfer"]["request_id"] == request_id
    assert listed.status_code == 200
    assert [item["request_id"] for item in listed.get_json()["items"]] == [
        request_id
    ]


# 8. Other citizens cannot access it.


def test_other_citizens_cannot_access_the_transfer(seed):
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]
    client = seed.app.test_client()

    detail = client.get(
        f"/api/transfers/{request_id}",
        headers=_headers(seed, seed.stranger.id),
    )
    listed = client.get(
        "/api/transfers", headers=_headers(seed, seed.stranger.id)
    )

    assert detail.status_code == 403
    assert listed.status_code == 200
    assert listed.get_json()["items"] == []


# 9. Buyer retains access after email changes.


def test_buyer_retains_access_after_email_change(seed):
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]

    with seed.app.app_context():
        buyer_model = db.session.get(UserModel, seed.buyer.id)
        buyer_model.email = "id-buyer-new@example.com"
        db.session.commit()

    client = seed.app.test_client()
    detail = client.get(
        f"/api/transfers/{request_id}", headers=_headers(seed, seed.buyer.id)
    )
    listed = client.get(
        "/api/transfers", headers=_headers(seed, seed.buyer.id)
    )
    # Review still works even though the stored reference email is stale.
    approved = _approve_http(seed, request_id)

    assert detail.status_code == 200
    assert detail.get_json()["transfer"]["request_id"] == request_id
    assert listed.status_code == 200
    assert [item["request_id"] for item in listed.get_json()["items"]] == [
        request_id
    ]
    assert approved.status_code == 200
    assert approved.get_json()["transfer"]["status"] == "APPROVED"


# 10. Ownership finalization uses the canonical buyer ID.


def test_finalization_uses_canonical_buyer_id(seed):
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]
    assert _approve_http(seed, request_id).status_code == 200

    # Start blockchain submission through the gateway boundary.
    seed.app.config["BLOCKCHAIN_GATEWAY"] = StubBlockchainGateway()
    submit = seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/blockchain/submit",
        headers=_headers(seed, seed.registrar.id, Role.REGISTRAR),
    )
    assert submit.status_code == 200

    with seed.app.app_context():
        # The buyer changes email, freeing their original address...
        buyer_model = db.session.get(UserModel, seed.buyer.id)
        buyer_model.email = "id-buyer-new@example.com"
        db.session.commit()
        # ...which another account now holds. The stored buyer_reference
        # would resolve to this wrong user; the canonical ID must win.
        db.session.add(
            UserModel(
                id="user-email-reuse",
                name="Email Reuse",
                email="id-buyer@example.com",
                password_hash=hash_password("reuse password"),
                role=Role.CITIZEN.value,
            )
        )
        db.session.commit()

        confirmed = StubBlockchainGateway(
            confirmation=_confirmation(request_id, seed.parcel_id)
        )
        completed = _service(seed, confirmed).finalize_transfer(
            seed.registrar.id, Role.REGISTRAR, request_id
        )
        records = seed.ownership_repository.list_for_parcel(seed.parcel_id)
        events = _service(seed, confirmed).list_ownership_events(
            seed.parcel_id
        )

    assert completed.status is TransferStatus.COMPLETED
    assert completed.buyer_id == seed.buyer.id

    active = [
        record
        for record in records
        if record.status == OwnershipStatus.ACTIVE
    ]
    assert [record.owner_id for record in active] == [seed.buyer.id]
    assert not any(
        record.owner_id == "user-email-reuse" for record in records
    )

    assert len(events) == 1
    assert events[0]["new_owner_id"] == seed.buyer.id
    assert events[0]["previous_owner_id"] == seed.seller.id


# 11. Existing transfer records remain safely readable.


def test_legacy_records_remain_safely_readable(seed):
    now = utc_now()
    with seed.app.app_context():
        legacy = TransferRequest(
            request_id=REQUEST_ID_LEGACY,
            parcel_id=seed.parcel_id,
            seller_id=seed.seller.id,
            buyer_reference=seed.buyer.email,
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        event = TransferAuditEvent(
            event_id="event-legacy-submit",
            request_id=REQUEST_ID_LEGACY,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seed.seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        seed.transfer_repository.create_request_with_audit(legacy, event)
        stored = seed.transfer_repository.find_by_id(REQUEST_ID_LEGACY)
    assert stored.buyer_id is None

    client = seed.app.test_client()
    detail = client.get(
        f"/api/transfers/{REQUEST_ID_LEGACY}",
        headers=_headers(seed, seed.buyer.id),
    )
    listed = client.get(
        "/api/transfers", headers=_headers(seed, seed.buyer.id)
    )

    # Legacy rows stay readable through the reference-based fallback, and the
    # response format keeps the same shape with buyer_id simply null.
    assert detail.status_code == 200
    body = detail.get_json()["transfer"]
    assert body["buyer_id"] is None
    assert body["buyer_reference"] == seed.buyer.email
    assert listed.status_code == 200
    assert [item["request_id"] for item in listed.get_json()["items"]] == [
        REQUEST_ID_LEGACY
    ]
    # Review still resolves the legacy reference.
    assert _approve_http(seed, REQUEST_ID_LEGACY).status_code == 200


# 12. A missing canonical buyer is never silently reassigned.


def test_finalization_never_reassigns_when_canonical_buyer_is_missing(seed):
    # Pending on-chain transfer whose canonical buyer no longer exists while
    # the legacy reference points at a different, valid citizen.
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]
    assert _approve_http(seed, request_id).status_code == 200
    seed.app.config["BLOCKCHAIN_GATEWAY"] = StubBlockchainGateway()
    submit = seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/blockchain/submit",
        headers=_headers(seed, seed.registrar.id, Role.REGISTRAR),
    )
    assert submit.status_code == 200

    with seed.app.app_context():
        stored = seed.transfer_repository.find_by_id(request_id)
        seed.transfer_repository.save_request(
            TransferRequest(
                **{
                    **stored.__dict__,
                    "buyer_reference": seed.stranger.email,
                    "buyer_id": "user-deleted-buyer",
                }
            )
        )
        confirmed = StubBlockchainGateway(
            confirmation=_confirmation(request_id, seed.parcel_id)
        )
        with pytest.raises(ResourceNotFoundError, match="buyer"):
            _service(seed, confirmed).finalize_transfer(
                seed.registrar.id, Role.REGISTRAR, request_id
            )

        records = seed.ownership_repository.list_for_parcel(seed.parcel_id)
        after = seed.transfer_repository.find_by_id(request_id)

    # Nothing changed: the transfer is still pending and ownership was never
    # handed to the stranger referenced by the stale reference.
    assert after.status is TransferStatus.BLOCKCHAIN_PENDING
    assert [record.owner_id for record in records] == [seed.seller.id]
    assert seed.stranger.id not in _active_owner_ids(seed)


def test_unapproved_transfer_cannot_be_finalized_by_identity_confusion(seed):
    # Approval remains the gate: identity resolution never lets a transfer
    # skip the review workflow.
    request_id = _submit(seed, seed.buyer.email).get_json()["transfer"][
        "request_id"
    ]

    with seed.app.app_context():
        confirmed = StubBlockchainGateway(
            confirmation=_confirmation(request_id, seed.parcel_id)
        )
        with pytest.raises(ResourceConflictError):
            _service(seed, confirmed).finalize_transfer(
                seed.registrar.id, Role.REGISTRAR, request_id
            )
        assert _active_owner_ids(seed) == [seed.seller.id]

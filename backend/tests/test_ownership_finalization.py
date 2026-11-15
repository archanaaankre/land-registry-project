"""Ownership finalization after verified blockchain confirmation.

Person 1 owns the real blockchain integration. These tests inject a stub
gateway behind the agreed ``BlockchainGateway`` interface so the
finalization workflow can be verified without any fake production
confirmation path: the service always reads confirmations from the gateway
boundary and never accepts them from callers.
"""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    RegistryUnavailableError,
    ResourceConflictError,
    ResourceNotFoundError,
)
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
from app.transfers.authorization import TRANSFER_FINALIZE_ROLES
from app.transfers.blockchain import (
    BlockchainConfirmation,
    BlockchainSubmission,
    UnavailableBlockchainGateway,
)
from app.transfers.services import TransferService

PARCEL_ID = "parcel-final"
REQUEST_ID = "transfer-final"
TX_ID = "0xfake-tx-1"


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "ownership_finalization.db").replace(
        "\\", "/"
    )


def _prepare_app(database_url):
    from app.config import Config

    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-ownership-finalization",
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

    def __init__(
        self,
        *,
        tx_id=TX_ID,
        submission_status=BlockchainSubmissionStatus.SUBMITTED,
        confirmation=None,
    ):
        self.tx_id = tx_id
        self.submission_status = submission_status
        self.confirmation = confirmation
        self.submitted_requests = []
        self.verified_requests = []

    def submit(self, request):
        self.submitted_requests.append(request.request_id)
        accepted = self.submission_status in (
            BlockchainSubmissionStatus.PENDING,
            BlockchainSubmissionStatus.SUBMITTED,
        )
        return BlockchainSubmission(
            request_id=request.request_id,
            status=self.submission_status,
            tx_id=self.tx_id if accepted else None,
            failure_reason=None if accepted else "stub submission failure",
        )

    def verify_confirmation(self, request_id):
        self.verified_requests.append(request_id)
        return self.confirmation


def _confirmation(
    seed,
    *,
    verified=True,
    status=BlockchainSubmissionStatus.CONFIRMED,
    tx_id=TX_ID,
    failure_reason=None,
):
    return BlockchainConfirmation(
        request_id=seed.request_id,
        parcel_id=seed.parcel_id,
        tx_id=tx_id,
        status=status,
        verified=verified,
        confirmed_at=utc_now(),
        failure_reason=failure_reason,
    )


def _seed(app, *, transfer_status=TransferStatus.BLOCKCHAIN_PENDING):
    """Create citizens, a registrar, a parcel, ownership, and a transfer."""
    user_repository = app.config["AUTH_USER_REPOSITORY"]
    parcel_repository = app.config["PARCEL_REPOSITORY"]
    ownership_repository = app.config["OWNERSHIP_REPOSITORY"]
    transfer_repository = app.config["TRANSFER_REPOSITORY"]
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="final-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="final-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        registrar = user_repository.create_user(
            name="Registrar",
            email="final-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id=PARCEL_ID,
                cadastral_number="CAD-FINAL",
                location="Ward Final",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-final-seller",
                parcel_id=PARCEL_ID,
                owner_id=seller.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        on_chain = transfer_status in (
            TransferStatus.BLOCKCHAIN_PENDING,
            TransferStatus.COMPLETED,
        )
        transfer = TransferRequest(
            request_id=REQUEST_ID,
            parcel_id=PARCEL_ID,
            seller_id=seller.id,
            buyer_reference=buyer.email,
            status=transfer_status,
            created_at=now,
            updated_at=now,
            reviewer_id=(
                None
                if transfer_status
                in (TransferStatus.DRAFT, TransferStatus.SUBMITTED)
                else registrar.id
            ),
            reviewed_at=(
                None
                if transfer_status
                in (TransferStatus.DRAFT, TransferStatus.SUBMITTED)
                else now
            ),
            blockchain_tx_id=TX_ID if on_chain else None,
            blockchain_status=(
                BlockchainSubmissionStatus.SUBMITTED
                if on_chain
                else (
                    BlockchainSubmissionStatus.NOT_SUBMITTED
                    if transfer_status == TransferStatus.SUBMITTED
                    else None
                )
            ),
        )
        submission_event = TransferAuditEvent(
            event_id="event-final-submit",
            request_id=REQUEST_ID,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller.id,
            actor_role=Role.CITIZEN,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        transfer_repository.create_request_with_audit(transfer, submission_event)

    return SimpleNamespace(
        app=app,
        seller=seller,
        buyer=buyer,
        registrar=registrar,
        parcel_id=PARCEL_ID,
        request_id=REQUEST_ID,
        user_repository=user_repository,
        parcel_repository=parcel_repository,
        ownership_repository=ownership_repository,
        transfer_repository=transfer_repository,
    )


@pytest.fixture
def pending(tmp_path):
    app, *_ = _prepare_app(_database_url(tmp_path))
    return _seed(app)


@pytest.fixture
def submitted(tmp_path):
    app, *_ = _prepare_app(_database_url(tmp_path))
    return _seed(app, transfer_status=TransferStatus.SUBMITTED)


def _service(seed, gateway):
    return TransferService(
        seed.transfer_repository,
        seed.parcel_repository,
        seed.ownership_repository,
        seed.user_repository,
        blockchain_gateway=gateway,
    )


def _finalize(seed, gateway, *, actor=None, role=Role.REGISTRAR):
    actor = actor or seed.registrar.id
    return _service(seed, gateway).finalize_transfer(
        actor, role, seed.request_id
    )


def _active_owner_ids(seed):
    with seed.app.app_context():
        records = seed.ownership_repository.list_for_parcel(seed.parcel_id)
    return [
        record.owner_id
        for record in records
        if record.status == OwnershipStatus.ACTIVE
    ]


def _transfer(seed):
    with seed.app.app_context():
        return seed.transfer_repository.find_by_id(seed.request_id)


def _approve(seed):
    return _service(seed, StubBlockchainGateway()).approve_request(
        seed.registrar.id, seed.request_id
    )


def _registrar_headers(seed):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            seed.registrar.id,
            Role.REGISTRAR,
            seed.app.config["JWT_SECRET_KEY"],
        )
    }


def _citizen_headers(seed, user_id):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id, Role.CITIZEN, seed.app.config["JWT_SECRET_KEY"]
        )
    }


# 1. Successful confirmed transfer updates ownership.


def test_successful_confirmed_transfer_updates_ownership(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        completed = _finalize(pending, gateway)

        assert completed.status is TransferStatus.COMPLETED
        assert completed.blockchain_status is (
            BlockchainSubmissionStatus.CONFIRMED
        )
        assert completed.blockchain_tx_id == TX_ID
        stored = pending.transfer_repository.find_by_id(pending.request_id)
        assert stored.status is TransferStatus.COMPLETED
        assert stored.blockchain_status is (
            BlockchainSubmissionStatus.CONFIRMED
        )


# 2. Seller ownership becomes inactive.


def test_seller_ownership_becomes_inactive(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        _finalize(pending, gateway)

        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )
        seller_records = [
            record
            for record in records
            if record.owner_id == pending.seller.id
        ]
        assert len(seller_records) == 1
        assert seller_records[0].status is OwnershipStatus.INACTIVE
        assert pending.seller.id not in _active_owner_ids(pending)


# 3. Buyer receives active ownership.


def test_buyer_receives_active_ownership(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        _finalize(pending, gateway)

        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )
        buyer_records = [
            record for record in records if record.owner_id == pending.buyer.id
        ]
        assert len(buyer_records) == 1
        assert buyer_records[0].status is OwnershipStatus.ACTIVE
        assert _active_owner_ids(pending) == [pending.buyer.id]


# 4. Transfer becomes COMPLETED (with audit trail).


def test_transfer_becomes_completed_with_finalization_audit(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        _finalize(pending, gateway)

        stored = pending.transfer_repository.find_by_id(pending.request_id)
        assert stored.status is TransferStatus.COMPLETED
        events = pending.transfer_repository.list_audit_events(
            pending.request_id
        )
        finalized = [
            event
            for event in events
            if event.event_type == "OWNERSHIP_FINALIZED"
        ]
        assert len(finalized) == 1
        assert finalized[0].from_status is TransferStatus.BLOCKCHAIN_PENDING
        assert finalized[0].to_status is TransferStatus.COMPLETED
        assert TX_ID in finalized[0].reason


# 5. Ownership history records the transfer with provenance.


def test_ownership_history_records_finalized_transfer(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        _finalize(pending, gateway)
        events = _service(pending, gateway).list_ownership_events(
            pending.parcel_id
        )
        legacy = OwnershipService(
            pending.ownership_repository, pending.parcel_repository
        ).list_history_for_parcel(pending.parcel_id)

    assert len(events) == 1
    entry = events[0]
    assert entry["parcel_id"] == pending.parcel_id
    assert entry["request_id"] == pending.request_id
    assert entry["previous_owner_id"] == pending.seller.id
    assert entry["new_owner_id"] == pending.buyer.id
    assert entry["blockchain_tx_id"] == TX_ID
    assert entry["finalized_at"]

    # The legacy status-based history keeps its existing shape and does not
    # invent provenance for rows it does not understand.
    assert [record.owner_id for record in legacy] == [pending.seller.id]
    assert all(
        record.status is OwnershipStatus.INACTIVE for record in legacy
    )

    client = pending.app.test_client()
    response = client.get(
        f"/api/parcels/{pending.parcel_id}/ownership/events",
        headers=_citizen_headers(pending, pending.seller.id),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["items"][0]["request_id"] == pending.request_id
    assert body["items"][0]["new_owner_id"] == pending.buyer.id


# 6. Approval without blockchain confirmation does not update ownership.


def test_approval_without_blockchain_confirmation_does_not_change_ownership(
    submitted,
):
    gateway = StubBlockchainGateway()
    with submitted.app.app_context():
        approved = _approve(submitted)
        assert approved.status is TransferStatus.APPROVED
        assert approved.blockchain_status is (
            BlockchainSubmissionStatus.UNAVAILABLE
        )
        assert _active_owner_ids(submitted) == [submitted.seller.id]

        with pytest.raises(ResourceConflictError):
            _finalize(submitted, gateway)

        # The gateway is never consulted for a transfer that is not pending
        # blockchain confirmation, and ownership is untouched.
        assert gateway.verified_requests == []
        assert _active_owner_ids(submitted) == [submitted.seller.id]
        assert _transfer(submitted).status is TransferStatus.APPROVED


# 7. Unconfirmed blockchain transaction does not update ownership.


@pytest.mark.parametrize("mode", ["missing", "unverified", "pending_status"])
def test_unconfirmed_blockchain_transaction_does_not_change_ownership(
    pending, mode
):
    confirmation = None
    if mode == "unverified":
        confirmation = _confirmation(pending, verified=False)
    elif mode == "pending_status":
        confirmation = _confirmation(
            pending, status=BlockchainSubmissionStatus.PENDING
        )
    gateway = StubBlockchainGateway(confirmation=confirmation)

    with pending.app.app_context():
        with pytest.raises(ResourceConflictError):
            _finalize(pending, gateway)

        assert _active_owner_ids(pending) == [pending.seller.id]
        stored = pending.transfer_repository.find_by_id(pending.request_id)
        assert stored.status is TransferStatus.BLOCKCHAIN_PENDING
        events = pending.transfer_repository.list_audit_events(
            pending.request_id
        )
        assert all(
            event.event_type != "OWNERSHIP_FINALIZED" for event in events
        )


def test_confirmation_must_match_the_stored_transaction(pending):
    gateway = StubBlockchainGateway(
        confirmation=_confirmation(pending, tx_id="0xother-tx")
    )
    with pending.app.app_context():
        with pytest.raises(ResourceConflictError, match="does not match"):
            _finalize(pending, gateway)

        assert _active_owner_ids(pending) == [pending.seller.id]
        assert _transfer(pending).status is TransferStatus.BLOCKCHAIN_PENDING


# 8. Failed transaction does not update ownership.


def test_failed_blockchain_transaction_does_not_change_ownership(pending):
    gateway = StubBlockchainGateway(
        confirmation=_confirmation(
            pending,
            status=BlockchainSubmissionStatus.FAILED,
            failure_reason="transaction reverted",
        )
    )
    with pending.app.app_context():
        with pytest.raises(ResourceConflictError, match="reverted"):
            _finalize(pending, gateway)

        assert _active_owner_ids(pending) == [pending.seller.id]
        stored = pending.transfer_repository.find_by_id(pending.request_id)
        assert stored.status is TransferStatus.BLOCKCHAIN_PENDING


# 9 & 10. Rejected and cancelled transfers cannot finalize.


@pytest.mark.parametrize(
    "status", [TransferStatus.REJECTED, TransferStatus.CANCELLED]
)
def test_rejected_or_cancelled_transfer_cannot_finalize(tmp_path, status):
    app, *_ = _prepare_app(_database_url(tmp_path))
    seed = _seed(app, transfer_status=status)
    gateway = StubBlockchainGateway(confirmation=_confirmation(seed))

    with app.app_context():
        with pytest.raises(ResourceConflictError):
            _finalize(seed, gateway)

        # The trusted gateway is never even consulted for terminal states.
        assert gateway.verified_requests == []
        assert _active_owner_ids(seed) == [seed.seller.id]
        assert _transfer(seed).status is status


# 11. Invalid buyer cannot receive ownership.


@pytest.mark.parametrize("mutation", ["non_citizen", "missing", "same_person"])
def test_invalid_buyer_cannot_receive_ownership(pending, mutation):
    with pending.app.app_context():
        transfer = pending.transfer_repository.find_by_id(pending.request_id)
        if mutation == "non_citizen":
            buyer_model = db.session.get(UserModel, pending.buyer.id)
            buyer_model.role = Role.REGISTRAR.value
            db.session.commit()
            expected_error = InvalidInputError
        elif mutation == "missing":
            pending.transfer_repository.save_request(
                TransferRequest(
                    **{
                        **transfer.__dict__,
                        "buyer_reference": "ghost-buyer@example.com",
                    }
                )
            )
            expected_error = ResourceNotFoundError
        else:
            pending.transfer_repository.save_request(
                TransferRequest(
                    **{**transfer.__dict__, "buyer_reference": pending.seller.id}
                )
            )
            expected_error = InvalidInputError

        gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
        with pytest.raises(expected_error):
            _finalize(pending, gateway)

        assert _active_owner_ids(pending) == [pending.seller.id]
        stored = pending.transfer_repository.find_by_id(pending.request_id)
        assert stored.status is TransferStatus.BLOCKCHAIN_PENDING
        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )
        assert all(
            record.owner_id != pending.buyer.id for record in records
        )


# 12. Repeated confirmation does not create duplicate ownership.


def test_repeated_confirmation_is_idempotent(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        service = _service(pending, gateway)
        first = service.finalize_transfer(
            pending.registrar.id, Role.REGISTRAR, pending.request_id
        )
        events_before = service.list_audit_events(
            pending.registrar.id, Role.REGISTRAR, pending.request_id
        )
        second = service.finalize_transfer(
            pending.registrar.id, Role.REGISTRAR, pending.request_id
        )
        events_after = service.list_audit_events(
            pending.registrar.id, Role.REGISTRAR, pending.request_id
        )
        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )

        assert first.status is TransferStatus.COMPLETED
        assert second.status is TransferStatus.COMPLETED
        assert len(events_after) == len(events_before)
        assert (
            len(
                [
                    event
                    for event in events_after
                    if event.event_type == "OWNERSHIP_FINALIZED"
                ]
            )
            == 1
        )
        assert len(records) == 2
        assert len(_active_owner_ids(pending)) == 1
        assert _active_owner_ids(pending) == [pending.buyer.id]


# 13. Database failure rolls back all finalization changes.


def test_database_failure_rolls_back_all_finalization_changes(pending):
    with pending.app.app_context():
        request = pending.transfer_repository.find_by_id(pending.request_id)
        finalized = TransferRequest(
            **{
                **request.__dict__,
                "status": TransferStatus.COMPLETED,
                "blockchain_tx_id": TX_ID,
                "blockchain_status": BlockchainSubmissionStatus.CONFIRMED,
                "updated_at": utc_now(),
            }
        )
        # A pre-existing audit row with the same primary key makes the final
        # commit fail after every other statement has executed.
        pending.transfer_repository.record_audit_event(
            TransferAuditEvent(
                event_id="event-finalize-duplicate",
                request_id=request.request_id,
                event_type="TRANSFER_SUBMITTED",
                actor_id=pending.seller.id,
                actor_role=Role.CITIZEN,
                from_status=None,
                to_status=TransferStatus.SUBMITTED,
                reason=None,
                created_at=utc_now(),
            )
        )
        failing_event = TransferAuditEvent(
            event_id="event-finalize-duplicate",
            request_id=request.request_id,
            event_type="OWNERSHIP_FINALIZED",
            actor_id=pending.registrar.id,
            actor_role=Role.REGISTRAR,
            from_status=TransferStatus.BLOCKCHAIN_PENDING,
            to_status=TransferStatus.COMPLETED,
            reason=f"Ownership finalized after verified blockchain transaction {TX_ID}.",
            created_at=utc_now(),
        )

        with pytest.raises(InvalidInputError):
            pending.transfer_repository.finalize_ownership(
                finalized,
                expected_status=TransferStatus.BLOCKCHAIN_PENDING,
                buyer_id=pending.buyer.id,
                buyer_ownership_id="ownership-rollback-test",
                event=failing_event,
            )

        stored = pending.transfer_repository.find_by_id(request.request_id)
        assert stored.status is TransferStatus.BLOCKCHAIN_PENDING
        assert stored.blockchain_status is BlockchainSubmissionStatus.SUBMITTED
        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )
        assert [
            (record.owner_id, record.status) for record in records
        ] == [(pending.seller.id, OwnershipStatus.ACTIVE)]
        events = pending.transfer_repository.list_audit_events(
            request.request_id
        )
        assert all(
            event.event_type != "OWNERSHIP_FINALIZED" for event in events
        )


# 14. Unauthorized confirmation attempts are rejected.


def test_unauthorized_finalization_attempts_are_rejected(pending):
    gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
    with pending.app.app_context():
        service = _service(pending, gateway)
        with pytest.raises(AuthorizationError):
            service.finalize_transfer(
                pending.seller.id, Role.CITIZEN, pending.request_id
            )
        with pytest.raises(AuthorizationError):
            service.finalize_transfer(
                pending.buyer.id, Role.CITIZEN, pending.request_id
            )
        # Citizens never reach the trusted gateway and never change state.
        assert gateway.verified_requests == []
        assert _active_owner_ids(pending) == [pending.seller.id]
        assert _transfer(pending).status is TransferStatus.BLOCKCHAIN_PENDING

    # No HTTP endpoint exists for a client to mark a transfer confirmed.
    client = pending.app.test_client()
    registrar_headers = _registrar_headers(pending)
    for path in (
        f"/api/registrar/transfers/{pending.request_id}/finalize",
        f"/api/transfers/{pending.request_id}/confirm",
    ):
        response = client.post(
            path,
            headers=registrar_headers,
            json={"blockchain_status": "CONFIRMED", "blockchain_tx_id": TX_ID},
        )
        assert response.status_code == 404

    # Citizens cannot trigger blockchain submission either.
    response = client.post(
        f"/api/registrar/transfers/{pending.request_id}/blockchain/submit",
        headers=_citizen_headers(pending, pending.seller.id),
    )
    assert response.status_code == 403
    assert _transfer(pending).status is TransferStatus.BLOCKCHAIN_PENDING


def test_finalization_role_policy_is_restricted():
    assert set(TRANSFER_FINALIZE_ROLES) == {Role.REGISTRAR, Role.ADMIN}
    assert Role.CITIZEN not in TRANSFER_FINALIZE_ROLES


# 15. Existing ownership share is preserved.


def test_ownership_share_is_preserved_on_finalization(pending):
    with pending.app.app_context():
        seller_record = next(
            record
            for record in pending.ownership_repository.list_for_parcel(
                pending.parcel_id
            )
            if record.owner_id == pending.seller.id
        )
        share_before = seller_record.share

        gateway = StubBlockchainGateway(confirmation=_confirmation(pending))
        _finalize(pending, gateway)

        records = pending.ownership_repository.list_for_parcel(
            pending.parcel_id
        )
        buyer_record = next(
            record
            for record in records
            if record.owner_id == pending.buyer.id
        )
        seller_after = next(
            record
            for record in records
            if record.owner_id == pending.seller.id
        )
        assert buyer_record.share == share_before == Decimal("100")
        assert seller_after.status is OwnershipStatus.INACTIVE
        active_total = sum(
            (
                record.share
                for record in records
                if record.status == OwnershipStatus.ACTIVE
            ),
            Decimal("0"),
        )
        assert active_total <= Decimal("100")


# Additional workflow and safety coverage.


def test_parcel_must_be_active_to_finalize(pending):
    for parcel_status in (ParcelStatus.DISPUTED, ParcelStatus.INACTIVE):
        with pending.app.app_context():
            pending.parcel_repository.update_parcel_status(
                pending.parcel_id,
                expected_status=ParcelStatus.ACTIVE,
                status=parcel_status,
                updated_at=utc_now(),
            )
            gateway = StubBlockchainGateway(
                confirmation=_confirmation(pending)
            )
            with pytest.raises(ResourceConflictError):
                _finalize(pending, gateway)

            assert pending.seller.id in _active_owner_ids(pending)
            assert _transfer(pending).status is TransferStatus.BLOCKCHAIN_PENDING
            pending.parcel_repository.update_parcel_status(
                pending.parcel_id,
                expected_status=parcel_status,
                status=ParcelStatus.ACTIVE,
                updated_at=utc_now(),
            )


def test_finalize_without_gateway_never_confirms(pending):
    with pending.app.app_context():
        with pytest.raises(
            ResourceConflictError, match="No verified blockchain confirmation"
        ):
            _service(pending, None).finalize_transfer(
                pending.registrar.id, Role.REGISTRAR, pending.request_id
            )
        assert _active_owner_ids(pending) == [pending.seller.id]
        assert _transfer(pending).status is TransferStatus.BLOCKCHAIN_PENDING


def test_unavailable_gateway_is_honest():
    gateway = UnavailableBlockchainGateway()
    submission = gateway.submit(SimpleNamespace(request_id="transfer-x"))
    assert submission.status is BlockchainSubmissionStatus.UNAVAILABLE
    assert gateway.verify_confirmation("transfer-x") is None


def test_approved_transfer_is_submitted_through_gateway(submitted):
    gateway = StubBlockchainGateway()
    with submitted.app.app_context():
        _approve(submitted)
        service = _service(submitted, gateway)
        in_flight = service.submit_to_blockchain(
            submitted.registrar.id, Role.REGISTRAR, submitted.request_id
        )

        assert in_flight.status is TransferStatus.BLOCKCHAIN_PENDING
        assert in_flight.blockchain_tx_id == TX_ID
        assert in_flight.blockchain_status is (
            BlockchainSubmissionStatus.SUBMITTED
        )
        assert gateway.submitted_requests == [submitted.request_id]
        events = submitted.transfer_repository.list_audit_events(
            submitted.request_id
        )
        assert "BLOCKCHAIN_SUBMITTED" in [
            event.event_type for event in events
        ]
        # Submission alone never changes ownership.
        assert _active_owner_ids(submitted) == [submitted.seller.id]


def test_submission_without_gateway_reports_unavailable(submitted):
    with submitted.app.app_context():
        _approve(submitted)
        with pytest.raises(RegistryUnavailableError):
            _service(submitted, None).submit_to_blockchain(
                submitted.registrar.id, Role.REGISTRAR, submitted.request_id
            )
        stored = submitted.transfer_repository.find_by_id(
            submitted.request_id
        )
        assert stored.status is TransferStatus.APPROVED
        assert stored.blockchain_status is (
            BlockchainSubmissionStatus.UNAVAILABLE
        )
        assert _active_owner_ids(submitted) == [submitted.seller.id]


def test_unapproved_transfer_cannot_be_submitted(submitted):
    gateway = StubBlockchainGateway()
    with submitted.app.app_context():
        with pytest.raises(ResourceConflictError):
            _service(submitted, gateway).submit_to_blockchain(
                submitted.registrar.id, Role.REGISTRAR, submitted.request_id
            )
        assert gateway.submitted_requests == []
        assert _transfer(submitted).status is TransferStatus.SUBMITTED


def test_registrar_submits_approved_transfer_through_endpoint(submitted):
    gateway = StubBlockchainGateway()
    submitted.app.config["BLOCKCHAIN_GATEWAY"] = gateway
    with submitted.app.app_context():
        _approve(submitted)

    client = submitted.app.test_client()
    response = client.post(
        f"/api/registrar/transfers/{submitted.request_id}/blockchain/submit",
        headers=_registrar_headers(submitted),
    )
    assert response.status_code == 200
    body = response.get_json()["transfer"]
    assert body["status"] == "BLOCKCHAIN_PENDING"
    assert body["blockchain_tx_id"] == TX_ID
    assert body["blockchain_status"] == "SUBMITTED"
    assert _active_owner_ids(submitted) == [submitted.seller.id]

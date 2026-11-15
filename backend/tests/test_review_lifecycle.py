"""Complete transfer review lifecycle: SUBMITTED -> UNDER_REVIEW.

`POST /api/registrar/transfers/<request_id>/review` is the explicit
reviewer-only operation that starts a review. It records the reviewer and
review timestamp on the transfer, writes exactly one TRANSFER_REVIEW_STARTED
audit event through the existing compare-and-set persistence conventions, and
is idempotent for repeated starts. Approval and rejection keep working from
UNDER_REVIEW; every other state is refused with a conflict.
"""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import AuthorizationError, ResourceConflictError
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
from app.transfers.services import TransferService

PARCEL_ID = "parcel-review"
SEED_REQUEST_ID = "transfer-seed"


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "review_lifecycle.db").replace("\\", "/")


def _prepare_app(database_url):
    from app.config import Config

    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-review-lifecycle",
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with app.app_context():
        db.create_all()
    app.config.update(
        AUTH_USER_REPOSITORY=SqlAlchemyUserRepository(),
        PARCEL_REPOSITORY=SqlAlchemyParcelRepository(),
        OWNERSHIP_REPOSITORY=SqlAlchemyOwnershipRepository(),
        TRANSFER_REPOSITORY=SqlAlchemyTransferRepository(),
    )
    return app


def _seed(app):
    user_repository = app.config["AUTH_USER_REPOSITORY"]
    parcel_repository = app.config["PARCEL_REPOSITORY"]
    ownership_repository = app.config["OWNERSHIP_REPOSITORY"]
    now = utc_now()
    with app.app_context():
        seller = user_repository.create_user(
            name="Seller",
            email="review-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = user_repository.create_user(
            name="Buyer",
            email="review-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        stranger = user_repository.create_user(
            name="Stranger",
            email="review-stranger@example.com",
            password_hash=hash_password("stranger password"),
            role=Role.CITIZEN,
        )
        registrar = user_repository.create_user(
            name="Registrar",
            email="review-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id=PARCEL_ID,
                cadastral_number="CAD-REV",
                location="Ward Review",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-review-seller",
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
    return _seed(_prepare_app(_database_url(tmp_path)))


def _headers(seed, user_id, role=Role.CITIZEN):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id, role, seed.app.config["JWT_SECRET_KEY"]
        )
    }


def _submit(seed):
    response = seed.app.test_client().post(
        "/api/transfers",
        headers=_headers(seed, seed.seller.id),
        json={"parcel_id": seed.parcel_id, "buyer_reference": seed.buyer.email},
    )
    assert response.status_code == 201
    return response.get_json()["transfer"]["request_id"]


def _start_review(seed, request_id, *, user_id=None, role=Role.REGISTRAR, body=None):
    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    return seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/review",
        headers=_headers(seed, user_id or seed.registrar.id, role),
        **kwargs,
    )


def _detail(seed, request_id, *, user_id=None, role=Role.REGISTRAR):
    return seed.app.test_client().get(
        f"/api/transfers/{request_id}",
        headers=_headers(seed, user_id or seed.registrar.id, role),
    )


def _approve(seed, request_id, *, body=None):
    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    return seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/approve",
        headers=_headers(seed, seed.registrar.id, Role.REGISTRAR),
        **kwargs,
    )


def _reject(seed, request_id, reason):
    return seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/reject",
        headers=_headers(seed, seed.registrar.id, Role.REGISTRAR),
        json={"reason": reason},
    )


def _seed_transfer_in_status(seed, status, request_id):
    """Create a transfer already sitting in a non-SUBMITTED state."""
    now = utc_now()
    with seed.app.app_context():
        transfer = TransferRequest(
            request_id=request_id,
            parcel_id=seed.parcel_id,
            seller_id=seed.seller.id,
            buyer_reference=seed.buyer.email,
            buyer_id=seed.buyer.id,
            status=status,
            created_at=now,
            updated_at=now,
            reviewer_id=seed.registrar.id
            if status is TransferStatus.REJECTED
            else None,
            reviewed_at=now if status is TransferStatus.REJECTED else None,
        )
        event = TransferAuditEvent(
            event_id=f"event-{request_id}-seed",
            request_id=request_id,
            event_type="TRANSFER_REJECTED"
            if status is TransferStatus.REJECTED
            else "TRANSFER_CANCELLED",
            actor_id=seed.registrar.id
            if status is TransferStatus.REJECTED
            else seed.seller.id,
            actor_role=Role.REGISTRAR
            if status is TransferStatus.REJECTED
            else Role.CITIZEN,
            from_status=TransferStatus.SUBMITTED,
            to_status=status,
            reason="seeded state" if status is TransferStatus.REJECTED else None,
            created_at=now,
        )
        seed.transfer_repository.create_request_with_audit(transfer, event)
    return request_id


def _audit_events(seed, request_id):
    with seed.app.app_context():
        return seed.transfer_repository.list_audit_events(request_id)


# Successful SUBMITTED -> UNDER_REVIEW transition.


def test_submitted_transfer_enters_under_review(seed):
    request_id = _submit(seed)

    response = _start_review(seed, request_id)

    assert response.status_code == 200
    body = response.get_json()["transfer"]
    assert body["request_id"] == request_id
    assert body["status"] == "UNDER_REVIEW"


# Reviewer identity and timestamp.


def test_reviewer_identity_and_timestamp_recorded(seed):
    request_id = _submit(seed)

    body = _start_review(seed, request_id).get_json()["transfer"]

    assert body["reviewer_id"] == seed.registrar.id
    assert body["reviewed_at"] is not None
    assert body["updated_at"] >= body["created_at"]
    # Starting a review without a reason leaves the reason empty.
    assert body["review_reason"] is None


# Audit event creation.


def test_review_start_records_audit_event(seed):
    request_id = _submit(seed)

    response = _start_review(
        seed, request_id, body={"reason": "checking ownership documents"}
    )
    assert response.status_code == 200

    detail = _detail(seed, request_id)
    history = detail.get_json()["history"]
    started = [
        event for event in history if event["event_type"] == "TRANSFER_REVIEW_STARTED"
    ]
    assert len(started) == 1
    event = started[0]
    assert event["request_id"] == request_id
    assert event["from_status"] == "SUBMITTED"
    assert event["to_status"] == "UNDER_REVIEW"
    assert event["actor_id"] == seed.registrar.id
    assert event["actor_role"] == "REGISTRAR"
    assert event["reason"] == "checking ownership documents"
    # The submission event is untouched.
    assert any(event["event_type"] == "TRANSFER_SUBMITTED" for event in history)
    assert response.get_json()["transfer"]["review_reason"] == (
        "checking ownership documents"
    )


# Citizens cannot start reviews.


@pytest.mark.parametrize("actor", ["buyer", "stranger"])
def test_citizen_cannot_start_review(seed, actor):
    request_id = _submit(seed)

    response = _start_review(
        seed, request_id, user_id=getattr(seed, actor).id, role=Role.CITIZEN
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
    stored = [
        item
        for item in _audit_events(seed, request_id)
        if item.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert stored == []


# Unauthorized roles are refused at the service layer too.


def test_service_rejects_unauthorized_reviewer(seed):
    request_id = _submit(seed)
    service = TransferService(
        seed.transfer_repository,
        seed.parcel_repository,
        seed.ownership_repository,
        seed.user_repository,
    )

    with seed.app.app_context():
        with pytest.raises(AuthorizationError, match="registrar"):
            service.start_review(seed.buyer.id, Role.CITIZEN, request_id)
        stored = seed.transfer_repository.find_by_id(request_id)

    assert stored.status is TransferStatus.SUBMITTED


def test_unauthenticated_cannot_start_review(seed):
    request_id = _submit(seed)

    response = seed.app.test_client().post(
        f"/api/registrar/transfers/{request_id}/review"
    )

    assert response.status_code == 401


# Missing transfer returns the appropriate error.


def test_missing_transfer_returns_not_found(seed):
    response = _start_review(seed, "transfer-missing")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


# Repeated review-start requests are idempotent: no duplicate audit events.


def test_repeated_start_review_is_idempotent(seed):
    request_id = _submit(seed)

    first = _start_review(seed, request_id)
    second = _start_review(
        seed, request_id, body={"reason": "duplicate start attempt"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["transfer"]["status"] == "UNDER_REVIEW"
    # The second call neither overwrites the reviewer nor records a reason.
    assert second.get_json()["transfer"]["reviewer_id"] == seed.registrar.id
    assert second.get_json()["transfer"]["review_reason"] is None
    started = [
        event
        for event in _audit_events(seed, request_id)
        if event.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert len(started) == 1


# Invalid states cannot enter UNDER_REVIEW.


def test_cancelled_transfer_cannot_enter_review(seed):
    request_id = _seed_transfer_in_status(
        seed, TransferStatus.CANCELLED, "transfer-cancelled"
    )

    response = _start_review(seed, request_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"
    stored = [
        event
        for event in _audit_events(seed, request_id)
        if event.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert stored == []


def test_rejected_transfer_cannot_enter_review(seed):
    request_id = _seed_transfer_in_status(
        seed, TransferStatus.REJECTED, "transfer-rejected"
    )

    response = _start_review(seed, request_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"


def test_approved_transfer_cannot_enter_review(seed):
    request_id = _submit(seed)
    assert _approve(seed, request_id).status_code == 200

    response = _start_review(seed, request_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"
    stored = [
        event
        for event in _audit_events(seed, request_id)
        if event.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert stored == []


# Concurrent review attempts cannot produce duplicate transitions or events.


def test_concurrent_start_review_cannot_duplicate_audit_event(seed):
    request_id = _submit(seed)
    assert _start_review(seed, request_id).status_code == 200

    with seed.app.app_context():
        stored = seed.transfer_repository.find_by_id(request_id)
        # A second reviewer that read the transfer while it was still
        # SUBMITTED tries to commit the same transition after the first
        # one already won: the compare-and-set must reject it.
        now = utc_now()
        contender = TransferRequest(
            **{
                **stored.__dict__,
                "reviewer_id": seed.registrar.id,
                "reviewed_at": now,
                "updated_at": now,
            }
        )
        losing_event = TransferAuditEvent(
            event_id="event-losing-review-start",
            request_id=request_id,
            event_type="TRANSFER_REVIEW_STARTED",
            actor_id=seed.registrar.id,
            actor_role=Role.REGISTRAR,
            from_status=TransferStatus.SUBMITTED,
            to_status=TransferStatus.UNDER_REVIEW,
            reason=None,
            created_at=now,
        )
        with pytest.raises(ResourceConflictError):
            seed.transfer_repository.save_request_with_audit(
                contender, TransferStatus.SUBMITTED, losing_event
            )
        events = seed.transfer_repository.list_audit_events(request_id)
        after = seed.transfer_repository.find_by_id(request_id)

    started = [
        event
        for event in events
        if event.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert len(started) == 1
    assert after.status is TransferStatus.UNDER_REVIEW
    assert after.reviewer_id == seed.registrar.id


# Approval and rejection still work after review starts.


def test_approval_still_works_after_review_starts(seed):
    request_id = _submit(seed)
    assert _start_review(seed, request_id).status_code == 200

    response = _approve(seed, request_id)

    assert response.status_code == 200
    body = response.get_json()["transfer"]
    assert body["status"] == "APPROVED"
    history = _detail(seed, request_id).get_json()["history"]
    assert any(event["event_type"] == "TRANSFER_APPROVED" for event in history)


def test_rejection_still_works_after_review_starts(seed):
    request_id = _submit(seed)
    assert _start_review(seed, request_id).status_code == 200

    response = _reject(seed, request_id, "title deed mismatch")

    assert response.status_code == 200
    body = response.get_json()["transfer"]
    assert body["status"] == "REJECTED"
    assert body["review_reason"] == "title deed mismatch"
    history = _detail(seed, request_id).get_json()["history"]
    assert any(event["event_type"] == "TRANSFER_REJECTED" for event in history)


# The optional body follows the existing review-decision validation.


def test_invalid_review_body_is_rejected(seed):
    request_id = _submit(seed)

    response = _start_review(seed, request_id, body={"comment": "hello"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"
    stored = [
        event
        for event in _audit_events(seed, request_id)
        if event.event_type == "TRANSFER_REVIEW_STARTED"
    ]
    assert stored == []

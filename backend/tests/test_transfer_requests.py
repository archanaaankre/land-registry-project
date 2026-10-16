from datetime import datetime, timezone
from decimal import Decimal
import secrets
from unittest.mock import Mock

import pytest

from app import create_app
from app.auth.service import create_access_token
from app.models import (
    AreaUnit,
    BlockchainSubmissionStatus,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
    TransferStatus,
    User,
)
from app.transfers.authorization import (
    TRANSFER_READ_ROLES,
    TRANSFER_REVIEW_ROLES,
    TRANSFER_SUBMIT_ROLES,
)
from app.transfers.repositories import TransferRepository


def bearer(app, role):
    token = create_access_token(
        f"{role.value.lower()}-1", role, app.config["JWT_SECRET_KEY"]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, JWT_SECRET_KEY=secrets.token_urlsafe(32))
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def ownership_record(owner_id="citizen-1"):
    now = datetime.now(timezone.utc)
    return Ownership(
        ownership_id="ownership-1",
        parcel_id="parcel-1",
        owner_id=owner_id,
        share=Decimal("100"),
        status=OwnershipStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def parcel_record():
    now = datetime.now(timezone.utc)
    return Parcel(
        parcel_id="parcel-1",
        cadastral_number="CAD-1",
        location="Ward 1",
        area=Decimal("10"),
        area_unit=AreaUnit.HECTARES,
        status=ParcelStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def user_record(email="buyer@example.com"):
    return User(
        id="buyer-1",
        email=email,
        password_hash="scrypt-hash",
        role=Role.CITIZEN,
        name="Buyer",
    )


def make_transfer(
    status=TransferStatus.SUBMITTED, seller_id="citizen-1", buyer_reference="buyer@example.com"
):
    from app.models import TransferRequest

    now = datetime.now(timezone.utc)
    return TransferRequest(
        request_id="request-1",
        parcel_id="parcel-1",
        seller_id=seller_id,
        buyer_reference=buyer_reference,
        status=status,
        created_at=now,
        updated_at=now,
        blockchain_status=BlockchainSubmissionStatus.NOT_SUBMITTED,
    )


def configure_repositories(app, transfer_repository, parcel_repository, ownership_repository, user_repository):
    app.config["TRANSFER_REPOSITORY"] = transfer_repository
    app.config["PARCEL_REPOSITORY"] = parcel_repository
    app.config["OWNERSHIP_REPOSITORY"] = ownership_repository
    app.config["AUTH_USER_REPOSITORY"] = user_repository


def test_unauthenticated_transfer_requests_are_rejected(client):
    response = client.get("/api/transfers")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_authentication"


def test_transfer_submission_requires_repository_or_reports_unavailable(app, client):
    response = client.post(
        "/api/transfers",
        headers=bearer(app, Role.CITIZEN),
        json={"parcel_id": "parcel-1", "buyer_reference": "buyer@example.com"},
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "registry_unavailable"


def test_citizen_cannot_submit_transfer_for_unowned_parcel(app, client):
    transfer_repository = Mock()
    transfer_repository.find_active_for_parcel.return_value = None
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = parcel_record()
    ownership_repository = Mock()
    ownership_repository.list_for_parcel.return_value = [ownership_record(owner_id="someone-else")]
    user_repository = Mock()
    user_repository.get_user_by_email.return_value = user_record()
    configure_repositories(
        app, transfer_repository, parcel_repository, ownership_repository, user_repository
    )

    response = client.post(
        "/api/transfers",
        headers=bearer(app, Role.CITIZEN),
        json={"parcel_id": "parcel-1", "buyer_reference": "buyer@example.com"},
    )
    assert response.status_code == 403


def test_citizen_cannot_submit_duplicate_active_transfer(app, client):
    existing = make_transfer(status=TransferStatus.UNDER_REVIEW)
    transfer_repository = Mock()
    transfer_repository.find_active_for_parcel.return_value = existing
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = parcel_record()
    ownership_repository = Mock()
    ownership_repository.list_for_parcel.return_value = [ownership_record()]
    user_repository = Mock()
    user_repository.get_user_by_email.return_value = user_record()
    configure_repositories(
        app, transfer_repository, parcel_repository, ownership_repository, user_repository
    )

    response = client.post(
        "/api/transfers",
        headers=bearer(app, Role.CITIZEN),
        json={"parcel_id": "parcel-1", "buyer_reference": "buyer@example.com"},
    )
    assert response.status_code == 409


def test_transfer_submission_does_not_change_ownership(app, client):
    transfer = make_transfer(status=TransferStatus.SUBMITTED)
    transfer_repository = Mock()
    transfer_repository.find_active_for_parcel.return_value = None
    transfer_repository.create_request.return_value = transfer
    transfer_repository.record_audit_event.side_effect = lambda event: event
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = parcel_record()
    ownership_repository = Mock()
    ownership_repository.list_for_parcel.return_value = [ownership_record()]
    user_repository = Mock()
    user_repository.get_user_by_email.return_value = user_record()
    configure_repositories(
        app, transfer_repository, parcel_repository, ownership_repository, user_repository
    )

    response = client.post(
        "/api/transfers",
        headers=bearer(app, Role.CITIZEN),
        json={"parcel_id": "parcel-1", "buyer_reference": "buyer@example.com"},
    )
    assert response.status_code == 201
    assert response.get_json()["transfer"]["status"] == "SUBMITTED"
    ownership_repository.assert_not_called()


def test_buyer_lookup_rejects_unknown_buyer(app, client):
    transfer_repository = Mock()
    transfer_repository.find_active_for_parcel.return_value = None
    parcel_repository = Mock()
    parcel_repository.find_by_id.return_value = parcel_record()
    ownership_repository = Mock()
    ownership_repository.list_for_parcel.return_value = [ownership_record()]
    user_repository = Mock()
    user_repository.get_user_by_email.return_value = None
    configure_repositories(
        app, transfer_repository, parcel_repository, ownership_repository, user_repository
    )

    response = client.post(
        "/api/transfers",
        headers=bearer(app, Role.CITIZEN),
        json={"parcel_id": "parcel-1", "buyer_reference": "missing@example.com"},
    )
    assert response.status_code == 404


def test_citizen_cannot_view_another_users_transfer(app, client):
    other = make_transfer(seller_id="someone-else")
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = other
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.get("/api/transfers/request-1", headers=bearer(app, Role.CITIZEN))
    assert response.status_code == 403


def test_citizen_cannot_cancel_another_users_transfer(app, client):
    other = make_transfer(seller_id="someone-else")
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = other
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/transfers/request-1/cancel",
        headers=bearer(app, Role.CITIZEN),
    )
    assert response.status_code == 403


def test_rejection_requires_reason(app, client):
    pending = make_transfer(status=TransferStatus.UNDER_REVIEW)
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = pending
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/registrar/transfers/request-1/reject",
        headers=bearer(app, Role.REGISTRAR),
        json={},
    )
    assert response.status_code == 400


def test_citizen_cannot_approve_transfer(app, client):
    pending = make_transfer(status=TransferStatus.UNDER_REVIEW)
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = pending
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/registrar/transfers/request-1/approve",
        headers=bearer(app, Role.CITIZEN),
    )
    assert response.status_code == 403


def test_registrar_cannot_approve_cancelled_transfer(app, client):
    cancelled = make_transfer(status=TransferStatus.CANCELLED)
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = cancelled
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/registrar/transfers/request-1/approve",
        headers=bearer(app, Role.REGISTRAR),
    )
    assert response.status_code == 409


def test_approved_transfer_does_not_change_ownership(app, client):
    pending = make_transfer(status=TransferStatus.UNDER_REVIEW)
    approved = make_transfer(status=TransferStatus.APPROVED)
    approved = approved.__class__(
        **{**approved.__dict__, "blockchain_status": BlockchainSubmissionStatus.UNAVAILABLE}
    )
    transfer_repository = Mock()
    transfer_repository.find_by_id.side_effect = [pending, approved]
    transfer_repository.save_request.return_value = approved
    transfer_repository.record_audit_event.side_effect = lambda event: event
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/registrar/transfers/request-1/approve",
        headers=bearer(app, Role.REGISTRAR),
    )
    assert response.status_code == 200
    body = response.get_json()["transfer"]
    assert body["status"] == "APPROVED"
    assert body["blockchain_status"] == "UNAVAILABLE"
    assert body["status"] != "COMPLETED"


def test_repeated_approval_is_idempotent(app, client):
    approved = make_transfer(status=TransferStatus.APPROVED)
    transfer_repository = Mock()
    transfer_repository.find_by_id.return_value = approved
    configure_repositories(
        app, transfer_repository, Mock(), Mock(), Mock()
    )

    response = client.post(
        "/api/registrar/transfers/request-1/approve",
        headers=bearer(app, Role.REGISTRAR),
    )
    assert response.status_code == 200
    assert response.get_json()["transfer"]["status"] == "APPROVED"


def test_transfer_read_roles_are_supported():
    assert set(TRANSFER_SUBMIT_ROLES) == {Role.CITIZEN}
    assert set(TRANSFER_READ_ROLES) == set(Role)
    assert set(TRANSFER_REVIEW_ROLES) == {Role.REGISTRAR}
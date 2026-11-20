"""Tests for supporting-document persistence, associations, and access control.

All tests use disposable SQLite databases via the ``seed`` fixture; no shared
PostgreSQL database is contacted and no migrations are executed.
"""

import hashlib
import io
import os
import secrets
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    ResourceNotFoundError,
)
from app.auth.service import create_access_token, hash_password
from app.config import Config
from app.document_integrity.models import SupportingDocument
from app.document_integrity.service import DocumentIntegrityService
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
    TransferRequest,
    TransferStatus,
    utc_now,
)
from app.persistence.repositories import (
    SqlAlchemyDocumentHashRepository,
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemySupportingDocumentRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
)

CONTENT = b"deed supporting evidence content"
MODIFIED_CONTENT = b"deed supporting evidence content - TAMPERED"
EXPECTED_HASH = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def seed(tmp_path):
    database_url = (
        "sqlite:///" + str(tmp_path / "supporting_documents.db").replace("\\", "/")
    )
    previous_url = os.environ.get("DATABASE_URL")
    previous_config_url = Config.SQLALCHEMY_DATABASE_URI
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    try:
        application = create_app()
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        Config.SQLALCHEMY_DATABASE_URI = previous_config_url

    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=database_url,
        MAX_DOCUMENT_UPLOAD_BYTES=1024,
    )
    user_repository = SqlAlchemyUserRepository()
    parcel_repository = SqlAlchemyParcelRepository()
    ownership_repository = SqlAlchemyOwnershipRepository()
    document_repository = SqlAlchemyDocumentHashRepository()
    supporting_document_repository = SqlAlchemySupportingDocumentRepository()
    transfer_repository = SqlAlchemyTransferRepository()
    application.config.update(
        AUTH_USER_REPOSITORY=user_repository,
        PARCEL_REPOSITORY=parcel_repository,
        OWNERSHIP_REPOSITORY=ownership_repository,
        DOCUMENT_HASH_REPOSITORY=document_repository,
        DOCUMENT_SUPPORTING_REPOSITORY=supporting_document_repository,
        TRANSFER_REPOSITORY=transfer_repository,
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
        stranger = user_repository.create_user(
            name="Unrelated Citizen",
            email="unrelated@example.com",
            password_hash=hash_password("a valid test password"),
            role=Role.CITIZEN,
        )
        now = utc_now()
        for parcel_id in ("parcel-owned", "parcel-unrelated"):
            parcel_repository.create_parcel(
                Parcel(
                    parcel_id=parcel_id,
                    cadastral_number=parcel_id.upper(),
                    location="Ward 1",
                    area=Decimal("10"),
                    area_unit=AreaUnit.SQ_METERS,
                    status=ParcelStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
        # The CITIZEN user actively owns "parcel-owned"; "stranger" actively
        # owns "parcel-unrelated".
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-owned",
                parcel_id="parcel-owned",
                owner_id=users[Role.CITIZEN].id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-unrelated",
                parcel_id="parcel-unrelated",
                owner_id=stranger.id,
                share=Decimal("100"),
                status=OwnershipStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )

    yield SimpleNamespace(
        app=application,
        client=application.test_client(),
        users=users,
        stranger=stranger,
        user_repository=user_repository,
        parcel_repository=parcel_repository,
        ownership_repository=ownership_repository,
        document_repository=document_repository,
        supporting_document_repository=supporting_document_repository,
        transfer_repository=transfer_repository,
    )
    with application.app_context():
        db.session.remove()
        db.drop_all()


def service(seed):
    return DocumentIntegrityService(
        seed.document_repository,
        seed.ownership_repository,
        supporting_document_repository=seed.supporting_document_repository,
        transfer_repository=seed.transfer_repository,
    )


def headers(seed, role, user=None):
    actor = user or seed.users[role]
    token = create_access_token(actor.id, role, seed.app.config["JWT_SECRET_KEY"])
    return {"Authorization": "Bearer " + token}


def create_transfer(
    seed,
    *,
    request_id="transfer-1",
    parcel_id="parcel-owned",
    seller,
    buyer=None,
    status=TransferStatus.SUBMITTED,
):
    now = utc_now()
    request = TransferRequest(
        request_id=request_id,
        parcel_id=parcel_id,
        seller_id=seller.id,
        buyer_reference=(
            buyer.email if buyer is not None else "buyer@example.com"
        ),
        buyer_id=buyer.id if buyer is not None else None,
        status=status,
        created_at=now,
        updated_at=now,
    )
    return seed.transfer_repository.create_request(request)


def upload_supporting(
    seed, role, *, content=CONTENT, name="Supporting", user=None, **extra_fields
):
    data = {
        "document": (io.BytesIO(content), "supporting.pdf"),
        "document_name": name,
    }
    for key, value in extra_fields.items():
        if value is not None:
            data[key] = value
    return seed.client.post(
        "/api/documents/upload",
        data=data,
        headers=headers(seed, role, user),
        content_type="multipart/form-data",
    )


# --- Persistence and retrieval ------------------------------------------------


def test_upload_persists_document_and_roundtrips_bytes(seed):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            uploaded_by=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )
        assert document.supporting_document_id.startswith("docsup-")
        stored = seed.supporting_document_repository.find_by_id(
            document.supporting_document_id
        )
        assert stored is not None
        assert stored.data == CONTENT
        assert stored.document_hash == EXPECTED_HASH
        assert stored.uploaded_by == seed.users[Role.CITIZEN].id
        assert stored.parcel_id is None
        assert stored.transfer_request_id is None


def test_upload_route_persists_and_returns_fields(seed):
    response = upload_supporting(seed, Role.CITIZEN, user=seed.users[Role.CITIZEN])
    assert response.status_code == 200
    body = response.get_json()["upload"]
    assert body["supporting_document_id"].startswith("docsup-")
    assert body["calculated_hash"] == EXPECTED_HASH
    assert body["document_hash"] == EXPECTED_HASH
    assert body["document_name"] == "Supporting"
    assert body["parcel_id"] is None
    assert body["transfer_request_id"] is None
    with seed.app.app_context():
        stored = seed.supporting_document_repository.find_by_id(
            body["supporting_document_id"]
        )
        assert stored is not None
        assert stored.data == CONTENT
        # Supporting documents must not appear in the trusted-hash listing.
        assert seed.document_repository.list_document_hashes() == []


def test_get_supporting_document_and_list_service_level(seed):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-owned",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        fetched = service(seed).get_supporting_document(
            document.supporting_document_id,
            actor_id=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        assert fetched is not None
        assert fetched.document_name == "Supporting"
        assert document.supporting_document_id in {
            doc.supporting_document_id
            for doc in service(seed).list_supporting_documents(
                actor_id=seed.users[Role.REGISTRAR].id, actor_role=Role.REGISTRAR
            )
        }
        assert (
            service(seed).get_supporting_document(
                "docsup-missing",
                actor_id=seed.users[Role.REGISTRAR].id,
                actor_role=Role.REGISTRAR,
            )
            is None
        )


# --- Parcel/request associations ------------------------------------------------


def test_upload_with_parcel_and_transfer_request_associations(seed):
    with seed.app.app_context():
        create_transfer(
            seed,
            parcel_id="parcel-owned",
            seller=seed.users[Role.CITIZEN],
            buyer=seed.users[Role.REGISTRAR],
        )
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-owned",
            transfer_request_id="transfer-1",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        assert document.parcel_id == "parcel-owned"
        assert document.transfer_request_id == "transfer-1"
        stored = seed.supporting_document_repository.find_by_id(
            document.supporting_document_id
        )
        assert stored.parcel_id == "parcel-owned"
        assert stored.transfer_request_id == "transfer-1"


def test_parcel_id_derived_from_transfer_request(seed):
    with seed.app.app_context():
        create_transfer(
            seed,
            parcel_id="parcel-owned",
            seller=seed.users[Role.CITIZEN],
            buyer=seed.users[Role.REGISTRAR],
        )
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            transfer_request_id="transfer-1",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        assert document.parcel_id == "parcel-owned"


def test_unknown_transfer_request_rejected(seed):
    with seed.app.app_context(), pytest.raises(ResourceNotFoundError):
        service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            transfer_request_id="transfer-missing",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )


def test_parcel_mismatch_rejected(seed):
    with seed.app.app_context():
        create_transfer(
            seed,
            parcel_id="parcel-owned",
            seller=seed.users[Role.CITIZEN],
        )
        with pytest.raises(InvalidInputError):
            service(seed).upload_supporting_document(
                document_name="Supporting",
                document_content=CONTENT,
                parcel_id="parcel-unrelated",
                transfer_request_id="transfer-1",
                uploaded_by=seed.users[Role.REGISTRAR].id,
                actor_role=Role.REGISTRAR,
            )


# --- Citizen upload authorization ------------------------------------------------


def test_citizen_cannot_attach_to_nonowned_parcel(seed):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-unrelated",
            uploaded_by=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )


def test_citizen_can_attach_to_owned_parcel(seed):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-owned",
            uploaded_by=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )
        assert document.parcel_id == "parcel-owned"


def test_citizen_cannot_attach_to_non_party_transfer_request(seed):
    with seed.app.app_context():
        create_transfer(
            seed,
            parcel_id="parcel-owned",
            seller=seed.users[Role.CITIZEN],
            buyer=seed.users[Role.REGISTRAR],
        )
        with pytest.raises(AuthorizationError):
            service(seed).upload_supporting_document(
                document_name="Supporting",
                document_content=CONTENT,
                transfer_request_id="transfer-1",
                uploaded_by=seed.stranger.id,
                actor_role=Role.CITIZEN,
            )


# --- Citizen access ----------------------------------------------------------------


def test_seller_and_buyer_can_access_docs_associated_with_transfer(seed):
    with seed.app.app_context():
        create_transfer(
            seed,
            parcel_id="parcel-owned",
            seller=seed.users[Role.CITIZEN],
            buyer=seed.stranger,
        )
        seller_doc = service(seed).upload_supporting_document(
            document_name="Seller evidence",
            document_content=CONTENT,
            transfer_request_id="transfer-1",
            uploaded_by=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )
        buyer_doc = service(seed).upload_supporting_document(
            document_name="Buyer evidence",
            document_content=MODIFIED_CONTENT,
            transfer_request_id="transfer-1",
            uploaded_by=seed.stranger.id,
            actor_role=Role.CITIZEN,
        )
        buyer_view = service(seed).get_supporting_document(
            seller_doc.supporting_document_id,
            actor_id=seed.stranger.id,
            actor_role=Role.CITIZEN,
        )
        assert buyer_view is not None
        seller_view = service(seed).get_supporting_document(
            buyer_doc.supporting_document_id,
            actor_id=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )
        assert seller_view is not None
        listed = {
            doc.supporting_document_id
            for doc in service(seed).list_supporting_documents(
                actor_id=seed.stranger.id, actor_role=Role.CITIZEN
            )
        }
        assert (
            {
                seller_doc.supporting_document_id,
                buyer_doc.supporting_document_id,
            }
            <= listed
        )


def test_citizen_can_see_own_uploads(seed):
    response = upload_supporting(
        seed, Role.CITIZEN, user=seed.users[Role.CITIZEN], name="My Deed"
    )
    assert response.status_code == 200
    doc_id = response.get_json()["upload"]["supporting_document_id"]
    listed = seed.client.get(
        "/api/documents/supporting",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert doc_id in {
        doc["supporting_document_id"] for doc in listed.get_json()["documents"]
    }
    fetched = seed.client.get(
        f"/api/documents/supporting/{doc_id}",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert fetched.status_code == 200


def test_citizen_active_owner_sees_documents_associated_with_parcel(seed):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-owned",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
    listed = seed.client.get(
        "/api/documents/supporting",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert document.supporting_document_id in {
        doc["supporting_document_id"] for doc in listed.get_json()["documents"]
    }


def test_unrelated_citizen_cannot_see_documents(seed):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-unrelated",
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        assert (
            service(seed).get_supporting_document(
                document.supporting_document_id,
                actor_id=seed.users[Role.CITIZEN].id,
                actor_role=Role.CITIZEN,
            )
            is None
        )
        listed = service(seed).list_supporting_documents(
            actor_id=seed.users[Role.CITIZEN].id, actor_role=Role.CITIZEN
        )
        assert document.supporting_document_id not in {
            doc.supporting_document_id for doc in listed
        }


def test_unrelated_citizen_gets_404_via_route(seed):
    response = upload_supporting(
        seed,
        Role.REGISTRAR,
        user=seed.users[Role.REGISTRAR],
        parcel_id="parcel-unrelated",
    )
    doc_id = response.get_json()["upload"]["supporting_document_id"]
    fetched = seed.client.get(
        f"/api/documents/supporting/{doc_id}",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert fetched.status_code == 404
    assert fetched.get_json()["error"]["code"] == "not_found"
    download = seed.client.get(
        f"/api/documents/supporting/{doc_id}/download",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert download.status_code == 404


# --- Privileged-role access ---------------------------------------------------------


@pytest.mark.parametrize(
    "role", [Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER]
)
def test_privileged_roles_see_all_supporting_documents(seed, role):
    with seed.app.app_context():
        document = service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            parcel_id="parcel-owned",
            uploaded_by=seed.users[Role.CITIZEN].id,
            actor_role=Role.CITIZEN,
        )
    listed = seed.client.get(
        "/api/documents/supporting",
        headers=headers(seed, role, seed.users[role]),
    )
    assert document.supporting_document_id in {
        doc["supporting_document_id"] for doc in listed.get_json()["documents"]
    }
    fetched = seed.client.get(
        f"/api/documents/supporting/{document.supporting_document_id}",
        headers=headers(seed, role, seed.users[role]),
    )
    assert fetched.status_code == 200


# --- Role restrictions ---------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [Role.REGISTRAR, Role.VERIFICATION_OFFICER, Role.CITIZEN]
)
def test_roles_can_upload_supporting_documents(seed, role):
    response = upload_supporting(seed, role, user=seed.users[role])
    assert response.status_code == 200
    assert response.get_json()["upload"]["calculated_hash"] == EXPECTED_HASH


def test_admin_cannot_upload_supporting_document(seed):
    response = upload_supporting(seed, Role.ADMIN)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


# --- Validation and size limits --------------------------------------------------------


def test_upload_route_rejects_invalid_filename(seed):
    response = upload_supporting(seed, Role.REGISTRAR, name="bad/name")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_upload_route_rejects_invalid_content_type(seed):
    response = upload_supporting(
        seed, Role.REGISTRAR, content_type="javascript:alert(1)"
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_upload_route_rejects_empty_content(seed):
    response = seed.client.post(
        "/api/documents/upload",
        data={
            "document": (io.BytesIO(b""), "empty.pdf"),
            "document_name": "Supporting",
        },
        headers=headers(seed, Role.REGISTRAR),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_oversized_upload_returns_structured_413(seed):
    seed.app.config.update(MAX_DOCUMENT_UPLOAD_BYTES=8)
    response = upload_supporting(seed, Role.REGISTRAR, content=b"x" * 9)
    assert response.status_code == 413
    assert response.get_json() == {
        "error": {
            "code": "payload_too_large",
            "message": "The uploaded document is too large.",
        }
    }


# --- Download ----------------------------------------------------------------------------


def test_download_supporting_document_route(seed):
    response = upload_supporting(seed, Role.REGISTRAR, user=seed.users[Role.REGISTRAR])
    doc_id = response.get_json()["upload"]["supporting_document_id"]
    download = seed.client.get(
        f"/api/documents/supporting/{doc_id}/download",
        headers=headers(seed, Role.REGISTRAR, seed.users[Role.REGISTRAR]),
    )
    assert download.status_code == 200
    assert download.data == CONTENT
    disposition = download.headers.get("Content-Disposition", "")
    assert disposition.startswith("attachment")
    assert doc_id in disposition
    assert download.headers.get("X-Content-Type-Options") == "nosniff"


def test_download_unrelated_citizen_gets_404(seed):
    response = upload_supporting(
        seed,
        Role.REGISTRAR,
        user=seed.users[Role.REGISTRAR],
        parcel_id="parcel-unrelated",
    )
    doc_id = response.get_json()["upload"]["supporting_document_id"]
    download = seed.client.get(
        f"/api/documents/supporting/{doc_id}/download",
        headers=headers(seed, Role.CITIZEN, seed.users[Role.CITIZEN]),
    )
    assert download.status_code == 404


def test_supporting_endpoints_require_authentication(seed):
    assert seed.client.get("/api/documents/supporting").status_code == 401
    assert seed.client.get("/api/documents/supporting/docsup-x").status_code == 401
    assert (
        seed.client.get("/api/documents/supporting/docsup-x/download").status_code
        == 401
    )


# --- Repository round-trip ------------------------------------------------------------------


def test_repository_create_find_and_list(seed):
    with seed.app.app_context():
        seed.supporting_document_repository.create_supporting_document(
            SupportingDocument(
                supporting_document_id="docsup-first",
                parcel_id="parcel-owned",
                transfer_request_id=None,
                document_name="First",
                document_hash=EXPECTED_HASH,
                data=CONTENT,
                content_type="application/pdf",
                uploaded_by=seed.users[Role.REGISTRAR].id,
                uploaded_at=utc_now(),
            )
        )
        seed.supporting_document_repository.create_supporting_document(
            SupportingDocument(
                supporting_document_id="docsup-second",
                parcel_id=None,
                transfer_request_id=None,
                document_name="Second",
                document_hash=EXPECTED_HASH,
                data=MODIFIED_CONTENT,
                content_type=None,
                uploaded_by=seed.users[Role.REGISTRAR].id,
                uploaded_at=utc_now(),
            )
        )
        stored = seed.supporting_document_repository.find_by_id("docsup-first")
        assert stored.data == CONTENT
        assert stored.document_name == "First"
        assert (
            seed.supporting_document_repository.find_by_id("docsup-missing") is None
        )
        assert {
            doc.supporting_document_id
            for doc in seed.supporting_document_repository.list_supporting_documents(
                parcel_id="parcel-owned"
            )
        } == {"docsup-first"}
        assert len(seed.supporting_document_repository.list_supporting_documents()) == 2

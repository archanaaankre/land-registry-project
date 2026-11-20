"""Document integrity: hashing, trusted baselines, verification, authorization.

These tests use a disposable SQLite database only; no shared PostgreSQL
instance is contacted and no migrations are executed.
"""

import hashlib
import io
import os
import secrets
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.auth.errors import AuthorizationError, ResourceConflictError
from app.auth.service import create_access_token, hash_password
from app.config import Config
from app.document_integrity.models import DocumentVerificationStatus
from app.document_integrity.service import DocumentIntegrityService
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
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

CONTENT = b"original title deed contents"
MODIFIED_CONTENT = b"original title deed contents - TAMPERED"
EXPECTED_HASH = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def seed(tmp_path):
    database_url = "sqlite:///" + str(
        tmp_path / "document_integrity.db"
    ).replace("\\", "/")
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
        owner = users[Role.CITIZEN]
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
                    created_by=users[Role.REGISTRAR].id,
                )
            )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-owned",
                parcel_id="parcel-owned",
                owner_id=owner.id,
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


def upload(seed, role, *, content=CONTENT, name="Deed", parcel_id="parcel-owned", user=None):
    data = {
        "document": (io.BytesIO(content), "deed.pdf"),
        "document_name": name,
    }
    if parcel_id is not None:
        data["parcel_id"] = parcel_id
    return seed.client.post(
        "/api/documents/hash",
        data=data,
        headers=headers(seed, role, user),
        content_type="multipart/form-data",
    )


def upload_supporting(seed, role, *, content=CONTENT, name="Supporting", user=None):
    return seed.client.post(
        "/api/documents/upload",
        data={
            "document": (io.BytesIO(content), "supporting.pdf"),
            "document_name": name,
        },
        headers=headers(seed, role, user),
        content_type="multipart/form-data",
    )


# --- SHA-256 correctness and baseline creation -----------------------------


def test_calculate_sha256_matches_known_digest(seed):
    assert service(seed).calculate_sha256(CONTENT) == EXPECTED_HASH
    assert service(seed).calculate_sha256(b"") == hashlib.sha256(b"").hexdigest()


def test_store_document_hash_persists_trusted_hash(seed):
    with seed.app.app_context():
        document = service(seed).store_document_hash(
            document_name="Deed",
            document_content=CONTENT,
            uploaded_by=seed.users[Role.REGISTRAR].id,
            parcel_id="parcel-owned",
            actor_role=Role.REGISTRAR,
        )
        assert document.document_hash == EXPECTED_HASH
        stored = seed.document_repository.find_by_id(document.document_id)
        assert stored.document_hash == EXPECTED_HASH
        assert stored.uploaded_by == seed.users[Role.REGISTRAR].id
        assert stored.parcel_id == "parcel-owned"
        assert stored.verification_count == 0


@pytest.mark.parametrize("content", [b"", bytearray()])
def test_empty_content_is_rejected(seed, content):
    with seed.app.app_context(), pytest.raises(Exception) as error:
        service(seed).store_document_hash(
            document_name="Deed",
            document_content=content,
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
    assert error.value.code == "invalid_input"


@pytest.mark.parametrize("name", ["", "   ", "bad/name", "x" * 201])
def test_invalid_document_name_is_rejected(seed, name):
    with seed.app.app_context(), pytest.raises(Exception) as error:
        service(seed).store_document_hash(
            document_name=name,
            document_content=CONTENT,
            uploaded_by=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
    assert error.value.code == "invalid_input"


def test_duplicate_name_for_same_parcel_is_rejected(seed):
    with seed.app.app_context():
        service(seed).store_document_hash(
            document_name="Deed",
            document_content=CONTENT,
            uploaded_by=seed.users[Role.REGISTRAR].id,
            parcel_id="parcel-owned",
            actor_role=Role.REGISTRAR,
        )
        with pytest.raises(ResourceConflictError):
            service(seed).store_document_hash(
                document_name="Deed",
                document_content=MODIFIED_CONTENT,
                uploaded_by=seed.users[Role.REGISTRAR].id,
                parcel_id="parcel-owned",
                actor_role=Role.REGISTRAR,
            )
        assert len(seed.document_repository.list_document_hashes()) == 1


# --- Verification and tamper detection ------------------------------------


def _store(seed, *, role=Role.REGISTRAR, user=None, parcel_id="parcel-owned"):
    with seed.app.app_context():
        return service(seed).store_document_hash(
            document_name="Deed",
            document_content=CONTENT,
            uploaded_by=(user or seed.users[role]).id,
            parcel_id=parcel_id,
            actor_role=role,
        )


def test_verification_matches_and_increments_count(seed):
    document = _store(seed)
    with seed.app.app_context():
        first = service(seed).verify_document(
            document.document_id,
            CONTENT,
            actor_id=seed.users[Role.VERIFICATION_OFFICER].id,
            actor_role=Role.VERIFICATION_OFFICER,
        )
        assert first.match is True
        assert first.status is DocumentVerificationStatus.MATCHED
        assert first.calculated_hash == EXPECTED_HASH
        assert first.failure_reason is None

        second = service(seed).verify_document(
            document.document_id,
            CONTENT,
            actor_id=seed.users[Role.REGISTRAR].id,
            actor_role=Role.REGISTRAR,
        )
        assert second.status is DocumentVerificationStatus.MATCHED
        assert second.calculated_hash == EXPECTED_HASH

        stored = seed.document_repository.find_by_id(document.document_id)
        assert stored.verification_count == 2
        assert stored.last_verification_status is DocumentVerificationStatus.MATCHED
        assert stored.last_verified_at is not None


def test_tampered_document_is_detected(seed):
    document = _store(seed)
    with seed.app.app_context():
        result = service(seed).verify_document(
            document.document_id,
            MODIFIED_CONTENT,
            actor_id=seed.users[Role.VERIFICATION_OFFICER].id,
            actor_role=Role.VERIFICATION_OFFICER,
        )
        assert result.match is False
        assert result.status is DocumentVerificationStatus.MISMATCHED
        assert result.calculated_hash == hashlib.sha256(MODIFIED_CONTENT).hexdigest()
        assert "modified" in result.failure_reason.lower()
        stored = seed.document_repository.find_by_id(document.document_id)
        assert stored.verification_count == 1
        assert stored.last_verification_status is DocumentVerificationStatus.MISMATCHED


def test_verification_of_unknown_document_is_not_found(seed):
    with seed.app.app_context(), pytest.raises(Exception) as error:
        service(seed).verify_document(
            "doc-missing",
            CONTENT,
            actor_id=seed.users[Role.VERIFICATION_OFFICER].id,
            actor_role=Role.VERIFICATION_OFFICER,
        )
    assert error.value.code == "not_found"


# --- Retrieval and listing -------------------------------------------------


def test_get_and_list_document_hashes(seed):
    first = _store(seed, parcel_id="parcel-owned")
    second = _store(seed, role=Role.REGISTRAR, parcel_id=None)
    with seed.app.app_context():
        assert seed.document_repository.find_by_id(first.document_id).document_name == "Deed"
        assert seed.document_repository.find_by_id("doc-missing") is None
        all_documents = service(seed).get_verification_history(
            actor_id=seed.users[Role.ADMIN].id, actor_role=Role.ADMIN
        )
        assert {d.document_id for d in all_documents} == {
            first.document_id,
            second.document_id,
        }
        scoped = service(seed).get_verification_history(
            parcel_id="parcel-owned",
            actor_id=seed.users[Role.ADMIN].id,
            actor_role=Role.ADMIN,
        )
        assert [d.document_id for d in scoped] == [first.document_id]
        assert (
            service(seed).get_document_hash(
                first.document_id,
                actor_id=seed.users[Role.ADMIN].id,
                actor_role=Role.ADMIN,
            ).document_id
            == first.document_id
        )


# --- HTTP authentication and role authorization ---------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/documents"),
        ("GET", "/api/documents/doc-1"),
        ("POST", "/api/documents/upload"),
        ("POST", "/api/documents/hash"),
        ("POST", "/api/documents/doc-1/verify"),
    ],
)
def test_document_endpoints_require_authentication(seed, method, path):
    response = seed.client.open(path, method=method)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_authentication"


def test_registrar_can_create_trusted_hash(seed):
    response = upload(seed, Role.REGISTRAR)
    assert response.status_code == 201
    assert response.get_json()["document"]["document_hash"] == EXPECTED_HASH


@pytest.mark.parametrize("role", [Role.ADMIN, Role.VERIFICATION_OFFICER, Role.CITIZEN])
def test_non_registrar_cannot_create_trusted_hash(seed, role):
    response = upload(seed, role, user=seed.users[role])
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.VERIFICATION_OFFICER, Role.CITIZEN])
def test_service_rejects_trusted_hash_creation_for_non_registrars(seed, role):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).store_document_hash(
            document_name="Deed",
            document_content=CONTENT,
            uploaded_by=seed.users[role].id,
            parcel_id="parcel-owned",
            actor_role=role,
        )


@pytest.mark.parametrize("role", [Role.REGISTRAR, Role.VERIFICATION_OFFICER, Role.CITIZEN])
def test_roles_can_upload_supporting_documents_without_creating_baseline(seed, role):
    response = upload_supporting(seed, role, user=seed.users[role])
    assert response.status_code == 200
    assert response.get_json()["upload"]["calculated_hash"] == EXPECTED_HASH
    with seed.app.app_context():
        assert seed.document_repository.list_document_hashes() == []


def test_admin_cannot_upload_supporting_document(seed):
    response = upload_supporting(seed, Role.ADMIN)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_service_rejects_supporting_upload_for_admin(seed):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).upload_supporting_document(
            document_name="Supporting",
            document_content=CONTENT,
            uploaded_by=seed.users[Role.ADMIN].id,
            actor_role=Role.ADMIN,
        )


def test_service_rejects_citizen_baseline_for_unowned_parcel(seed):
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).store_document_hash(
            document_name="Deed",
            document_content=CONTENT,
            uploaded_by=seed.stranger.id,
            parcel_id="parcel-owned",
            actor_role=Role.CITIZEN,
        )


@pytest.mark.parametrize("role", [Role.REGISTRAR, Role.VERIFICATION_OFFICER, Role.ADMIN])
def test_privileged_roles_can_verify_any_document(seed, role):
    document = _store(seed)
    response = seed.client.post(
        f"/api/documents/{document.document_id}/verify",
        data={"document": (io.BytesIO(CONTENT), "deed.pdf")},
        headers=headers(seed, role),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["verification"]["match"] is True


def test_owner_citizen_can_verify_document_for_owned_parcel(seed):
    document = _store(seed)
    response = seed.client.post(
        f"/api/documents/{document.document_id}/verify",
        data={"document": (io.BytesIO(CONTENT), "deed.pdf")},
        headers=headers(seed, Role.CITIZEN),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["verification"]["match"] is True


def test_unrelated_citizen_cannot_verify_document(seed):
    document = _store(seed)
    response = seed.client.post(
        f"/api/documents/{document.document_id}/verify",
        data={"document": (io.BytesIO(CONTENT), "deed.pdf")},
        headers=headers(seed, Role.CITIZEN, seed.stranger),
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_service_rejects_citizen_verification_of_unrelated_document(seed):
    document = _store(seed)
    with seed.app.app_context(), pytest.raises(AuthorizationError):
        service(seed).verify_document(
            document.document_id,
            CONTENT,
            actor_id=seed.stranger.id,
            actor_role=Role.CITIZEN,
        )


@pytest.mark.parametrize("role", list(Role))
def test_list_and_get_document_endpoints_for_all_roles(seed, role):
    document = _store(seed)
    listed = seed.client.get("/api/documents", headers=headers(seed, role))
    fetched = seed.client.get(
        f"/api/documents/{document.document_id}", headers=headers(seed, role)
    )
    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert fetched.get_json()["document"]["document_hash"] == EXPECTED_HASH


# --- Citizen-scoped document listing and detail ---------------------------


def test_citizen_can_list_and_get_documents_for_owned_parcel(seed):
    document = _store(seed, parcel_id="parcel-owned")
    citizen_headers = headers(seed, Role.CITIZEN)

    listed = seed.client.get("/api/documents", headers=citizen_headers)
    fetched = seed.client.get(
        f"/api/documents/{document.document_id}", headers=citizen_headers
    )

    assert listed.status_code == 200
    assert document.document_id in {
        item["document_id"] for item in listed.get_json()["documents"]
    }
    assert fetched.status_code == 200
    assert fetched.get_json()["document"]["document_hash"] == EXPECTED_HASH


def test_citizen_can_access_document_they_uploaded_without_ownership(seed):
    with seed.app.app_context():
        uploaded = service(seed).store_document_hash(
            document_name="UploadedByCitizen",
            document_content=CONTENT,
            uploaded_by=seed.stranger.id,
            parcel_id="parcel-owned",
            actor_role=Role.REGISTRAR,
        )
    citizen_headers = headers(seed, Role.CITIZEN, seed.stranger)

    listed = seed.client.get("/api/documents", headers=citizen_headers)
    fetched = seed.client.get(
        f"/api/documents/{uploaded.document_id}", headers=citizen_headers
    )

    assert uploaded.document_id in {
        item["document_id"] for item in listed.get_json()["documents"]
    }
    assert fetched.status_code == 200
    assert fetched.get_json()["document"]["uploaded_by"] == seed.stranger.id


def test_citizen_cannot_list_unrelated_documents(seed):
    unrelated = _store(seed, parcel_id="parcel-owned")
    response = seed.client.get(
        "/api/documents", headers=headers(seed, Role.CITIZEN, seed.stranger)
    )

    assert response.status_code == 200
    assert unrelated.document_id not in {
        item["document_id"] for item in response.get_json()["documents"]
    }


def test_citizen_cannot_get_unrelated_document_by_id(seed):
    unrelated = _store(seed, parcel_id="parcel-owned")
    response = seed.client.get(
        f"/api/documents/{unrelated.document_id}",
        headers=headers(seed, Role.CITIZEN, seed.stranger),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"
    assert EXPECTED_HASH not in response.get_data(as_text=True)
    assert unrelated.document_name not in response.get_data(as_text=True)


@pytest.mark.parametrize("role", [Role.REGISTRAR, Role.VERIFICATION_OFFICER, Role.ADMIN])
def test_privileged_roles_retain_unrestricted_document_read_access(seed, role):
    document = _store(seed, parcel_id="parcel-owned")
    listed = seed.client.get("/api/documents", headers=headers(seed, role))
    fetched = seed.client.get(
        f"/api/documents/{document.document_id}", headers=headers(seed, role)
    )

    assert listed.status_code == 200
    assert document.document_id in {
        item["document_id"] for item in listed.get_json()["documents"]
    }
    assert fetched.status_code == 200
    assert fetched.get_json()["document"]["document_hash"] == EXPECTED_HASH


def test_service_hides_unrelated_document_from_citizen(seed):
    unrelated = _store(seed, parcel_id="parcel-owned")
    with seed.app.app_context():
        assert (
            service(seed).get_document_hash(
                unrelated.document_id,
                actor_id=seed.stranger.id,
                actor_role=Role.CITIZEN,
            )
            is None
        )
        visible = service(seed).get_verification_history(
            actor_id=seed.stranger.id, actor_role=Role.CITIZEN
        )
        assert unrelated.document_id not in {doc.document_id for doc in visible}


# --- Upload size and validation -------------------------------------------


def test_oversized_upload_returns_structured_413(seed):
    seed.app.config.update(MAX_DOCUMENT_UPLOAD_BYTES=8)
    response = upload(seed, Role.REGISTRAR, content=b"x" * 9)
    assert response.status_code == 413
    assert response.get_json() == {
        "error": {
            "code": "payload_too_large",
            "message": "The uploaded document is too large.",
        }
    }
    with seed.app.app_context():
        assert seed.document_repository.list_document_hashes() == []


def test_oversized_verification_upload_returns_structured_413(seed):
    document = _store(seed)
    seed.app.config.update(MAX_DOCUMENT_UPLOAD_BYTES=8)
    response = seed.client.post(
        f"/api/documents/{document.document_id}/verify",
        data={"document": (io.BytesIO(b"x" * 9), "deed.pdf")},
        headers=headers(seed, Role.VERIFICATION_OFFICER),
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "payload_too_large"


def test_empty_upload_is_rejected_by_route(seed):
    response = upload(seed, Role.REGISTRAR, content=b"")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_missing_file_or_name_is_rejected_by_route(seed):
    missing_file = seed.client.post(
        "/api/documents/hash",
        data={"document_name": "Deed"},
        headers=headers(seed, Role.REGISTRAR),
        content_type="multipart/form-data",
    )
    missing_name = seed.client.post(
        "/api/documents/hash",
        data={"document": (io.BytesIO(CONTENT), "deed.pdf")},
        headers=headers(seed, Role.REGISTRAR),
        content_type="multipart/form-data",
    )
    assert missing_file.status_code == 400
    assert missing_name.status_code == 400

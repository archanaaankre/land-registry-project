"""Integration tests for the ownership Merkle APIs (Flask test client, SQLite)."""

import hashlib
import os
from decimal import Decimal

from app import create_app, db
from app.auth.service import create_access_token, hash_password
from app.config import Config
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
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemyUserRepository,
)
from app.registry.merkle import (
    canonical_leaf,
    generate_proof,
    merkle_root,
    sorted_leaves,
    verify_merkle_proof,
)


def _database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "merkle.db").replace("\\", "/")


def _prepare_app(database_url):
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-merkle",
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with app.app_context():
        db.create_all()
    user_repository = SqlAlchemyUserRepository()
    parcel_repository = SqlAlchemyParcelRepository()
    ownership_repository = SqlAlchemyOwnershipRepository()
    app.config.update(
        AUTH_USER_REPOSITORY=user_repository,
        PARCEL_REPOSITORY=parcel_repository,
        OWNERSHIP_REPOSITORY=ownership_repository,
    )
    return app, user_repository, parcel_repository, ownership_repository


def _headers(app, user_id, role):
    token = create_access_token(user_id, role, app.config["JWT_SECRET_KEY"])
    return {"Authorization": "Bearer " + token}


def _seed(app, user_repository, parcel_repository, ownership_repository):
    with app.app_context():
        citizen = user_repository.create_user(
            name="Asha Rao",
            email="asha@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.CITIZEN,
        )
        other = user_repository.create_user(
            name="Ben Rise",
            email="ben@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.CITIZEN,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-1",
                cadastral_number="CAD-M1",
                location="Ward 1",
                area=Decimal("2.5"),
                area_unit=AreaUnit.HECTARES,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        ownership_repository.create_ownership(
            Ownership(
                ownership_id="ownership-1",
                parcel_id="parcel-1",
                owner_id=citizen.id,
                share=Decimal("60.000000"),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        return citizen, other


def _add_ownership(app, ownership_repository, ownership_id, owner_id, share):
    with app.app_context():
        ownership_repository.create_ownership(
            Ownership(
                ownership_id=ownership_id,
                parcel_id="parcel-1",
                owner_id=owner_id,
                share=Decimal(share),
                status=OwnershipStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )


def _sorted_records(app, ownership_repository, parcel_id):
    with app.app_context():
        return sorted(
            ownership_repository.list_for_parcel(parcel_id),
            key=lambda r: r.ownership_id,
        )


def test_merkle_root_endpoint(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, _other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.get(
        "/api/parcels/parcel-1/ownership/merkle-root", headers=headers
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["parcel_id"] == "parcel-1"
    assert body["ownership_count"] == 1
    records = _sorted_records(app, ownership_repository, "parcel-1")
    assert body["merkle_root"] == merkle_root(sorted_leaves(records))


def test_merkle_root_endpoint_empty_for_parcel_without_ownership(tmp_path):
    app, user_repository, parcel_repository, _ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    with app.app_context():
        citizen = user_repository.create_user(
            name="Asha Rao",
            email="asha@example.com",
            password_hash=hash_password("valid test password"),
            role=Role.CITIZEN,
        )
        parcel_repository.create_parcel(
            Parcel(
                parcel_id="parcel-empty",
                cadastral_number="CAD-M2",
                location="Ward 2",
                area=Decimal("1.0"),
                area_unit=AreaUnit.SQ_METERS,
                status=ParcelStatus.ACTIVE,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.get(
        "/api/parcels/parcel-empty/ownership/merkle-root", headers=headers
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["parcel_id"] == "parcel-empty"
    assert body["ownership_count"] == 0
    assert body["merkle_root"] == hashlib.sha256(b"").hexdigest()


def test_merkle_root_changes_when_an_ownership_is_added(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    before = client.get(
        "/api/parcels/parcel-1/ownership/merkle-root", headers=headers
    )
    assert before.status_code == 200
    root_before = before.get_json()["merkle_root"]

    _add_ownership(app, ownership_repository, "ownership-2", other.id, "40.000000")

    after = client.get(
        "/api/parcels/parcel-1/ownership/merkle-root", headers=headers
    )
    assert after.status_code == 200
    assert after.get_json()["merkle_root"] != root_before
    assert after.get_json()["ownership_count"] == 2


def test_merkle_proofs_endpoint_returns_leaf_and_proof(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, other = _seed(app, user_repository, parcel_repository, ownership_repository)
    _add_ownership(app, ownership_repository, "ownership-2", other.id, "40.000000")
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.post(
        "/api/parcels/parcel-1/ownership/proofs",
        headers=headers,
        json={"ownership_id": "ownership-1"},
    )

    assert response.status_code == 200
    body = response.get_json()
    records = _sorted_records(app, ownership_repository, "parcel-1")
    ordered = [r.ownership_id for r in records]
    index = ordered.index("ownership-1")
    assert body["parcel_id"] == "parcel-1"
    assert body["ownership_id"] == "ownership-1"
    assert body["leaf_index"] == index
    assert body["leaf"] == canonical_leaf(records[index])
    assert body["proof"] == generate_proof(sorted_leaves(records), index)
    assert verify_merkle_proof(body["merkle_root"], body["leaf"], body["proof"])


def test_merkle_proofs_endpoint_404_for_unknown_ownership(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, _other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.post(
        "/api/parcels/parcel-1/ownership/proofs",
        headers=headers,
        json={"ownership_id": "ownership-missing"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_merkle_proofs_endpoint_400_for_invalid_ownership_id(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, _other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.post(
        "/api/parcels/parcel-1/ownership/proofs",
        headers=headers,
        json={"ownership_id": "!!!"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_merkle_proof_verify_endpoint_valid(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, other = _seed(app, user_repository, parcel_repository, ownership_repository)
    _add_ownership(app, ownership_repository, "ownership-2", other.id, "40.000000")
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    proof_response = client.post(
        "/api/parcels/parcel-1/ownership/proofs",
        headers=headers,
        json={"ownership_id": "ownership-1"},
    )
    assert proof_response.status_code == 200
    proof = proof_response.get_json()["proof"]

    response = client.post(
        "/api/parcels/parcel-1/ownership/proof-verify",
        headers=headers,
        json={"ownership_id": "ownership-1", "proof": proof},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is True
    assert body["parcel_id"] == "parcel-1"
    assert body["ownership_id"] == "ownership-1"
    assert body["merkle_root"] == proof_response.get_json()["merkle_root"]
    assert isinstance(body["leaf_index"], int)


def test_merkle_proof_verify_endpoint_rejects_tampered_proof(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, other = _seed(app, user_repository, parcel_repository, ownership_repository)
    _add_ownership(app, ownership_repository, "ownership-2", other.id, "40.000000")
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    proof_response = client.post(
        "/api/parcels/parcel-1/ownership/proofs",
        headers=headers,
        json={"ownership_id": "ownership-1"},
    )
    proof = proof_response.get_json()["proof"]
    assert proof
    tampered = [{**step, "hash": "f" * 64} for step in proof]

    response = client.post(
        "/api/parcels/parcel-1/ownership/proof-verify",
        headers=headers,
        json={"ownership_id": "ownership-1", "proof": tampered},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is False
    assert body["reason"] == "Merkle root mismatch."


def test_merkle_proof_verify_endpoint_400_for_malformed_proof(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, _other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    bad_bodies = [
        {"ownership_id": "ownership-1"},  # proof missing
        {"ownership_id": "ownership-1", "proof": "not-a-list"},
        {"ownership_id": "ownership-1", "proof": [{"hash": "short", "side": "right"}]},
        {"ownership_id": "ownership-1", "proof": [{"hash": "f" * 64, "side": "sideways"}]},
        {
            "ownership_id": "ownership-1",
            "proof": [{"hash": "Z" * 64, "side": "right"}],  # non-hex
        },
    ]
    for body in bad_bodies:
        response = client.post(
            "/api/parcels/parcel-1/ownership/proof-verify",
            headers=headers,
            json=body,
        )
        assert response.status_code == 400, body


def test_merkle_proof_verify_endpoint_404_for_unknown_ownership(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    citizen, _other = _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()
    headers = _headers(app, citizen.id, Role.CITIZEN)

    response = client.post(
        "/api/parcels/parcel-1/ownership/proof-verify",
        headers=headers,
        json={"ownership_id": "ownership-missing", "proof": []},
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_merkle_endpoints_require_authentication(tmp_path):
    app, user_repository, parcel_repository, ownership_repository = _prepare_app(
        _database_url(tmp_path)
    )
    _seed(app, user_repository, parcel_repository, ownership_repository)
    client = app.test_client()

    assert (
        client.get("/api/parcels/parcel-1/ownership/merkle-root").status_code == 401
    )
    assert (
        client.post(
            "/api/parcels/parcel-1/ownership/proofs",
            json={"ownership_id": "ownership-1"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/parcels/parcel-1/ownership/proof-verify",
            json={"ownership_id": "ownership-1", "proof": []},
        ).status_code
        == 401
    )

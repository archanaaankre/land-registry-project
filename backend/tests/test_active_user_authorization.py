"""Regression tests for active-user verification in ``roles_required``.

Every authenticated request must prove that the referenced account exists
and is active (``is_active=True``); a valid JWT alone is no longer enough.
The JWT role claim remains the authorization source (no DB-derived role).
"""

import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest

from app import create_app
from app.auth.service import create_access_token
from app.models import Role, User


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
    )
    return application


@pytest.fixture
def active_users():
    now = datetime.now(timezone.utc)
    return {
        Role.CITIZEN: User(
            id="citizen-active", email="citizen-active@example.com",
            password_hash="hash", role=Role.CITIZEN, name="Citizen Active",
            is_active=True, created_at=now, updated_at=now,
        ),
        Role.REGISTRAR: User(
            id="registrar-active", email="registrar-active@example.com",
            password_hash="hash", role=Role.REGISTRAR, name="Registrar Active",
            is_active=True, created_at=now, updated_at=now,
        ),
        Role.VERIFICATION_OFFICER: User(
            id="vo-active", email="vo-active@example.com",
            password_hash="hash", role=Role.VERIFICATION_OFFICER,
            name="Verifier Active", is_active=True,
            created_at=now, updated_at=now,
        ),
        Role.ADMIN: User(
            id="admin-active", email="admin-active@example.com",
            password_hash="hash", role=Role.ADMIN, name="Admin Active",
            is_active=True, created_at=now, updated_at=now,
        ),
    }


@pytest.fixture
def user_repository(active_users):
    repository = Mock()
    users = {
        user.id: user for user in active_users.values()
    }

    def get_user_by_id(user_id):
        return users.get(user_id)

    repository.get_user_by_id.side_effect = get_user_by_id
    repository.list_users.side_effect = (
        lambda search=None, role=None, is_active=None: list(users.values())
    )
    repository._users = users
    return repository


@pytest.fixture
def client(app, user_repository):
    app.config["AUTH_USER_REPOSITORY"] = user_repository
    return app.test_client()


def deactivate(user_repository, user_id):
    current = user_repository._users[user_id]
    user_repository._users[user_id] = replace(current, is_active=False)


def bearer(app, user, role=None):
    token = create_access_token(
        user.id, role or user.role, app.config["JWT_SECRET_KEY"]
    )
    return {"Authorization": f"Bearer {token}"}


# --- Active accounts are accepted, inactive are rejected (per role) -----------------


def test_active_citizen_is_authorized(app, client, user_repository, active_users):
    user = active_users[Role.CITIZEN]

    me = client.get("/api/auth/me", headers=bearer(app, user))
    assert me.status_code == 200
    assert me.get_json()["user"] == {"id": user.id, "role": "CITIZEN"}


def test_inactive_citizen_is_rejected(app, client, user_repository, active_users):
    user = active_users[Role.CITIZEN]
    deactivate(user_repository, user.id)

    response = client.get("/api/auth/me", headers=bearer(app, user))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
    assert response.get_json()["error"]["message"] == "Account is deactivated."


def test_active_registrar_is_authorized(app, client, user_repository, active_users):
    app.config["TRANSFER_REPOSITORY"] = Mock(
        list_pending_for_review=lambda: []
    )
    app.config["PARCEL_REPOSITORY"] = Mock()
    app.config["OWNERSHIP_REPOSITORY"] = Mock()
    user = active_users[Role.REGISTRAR]

    response = client.get(
        "/api/registrar/transfers", headers=bearer(app, user)
    )

    assert response.status_code == 200
    assert response.get_json() == {"items": []}


def test_inactive_registrar_is_rejected(app, client, user_repository, active_users):
    app.config["TRANSFER_REPOSITORY"] = Mock(
        list_pending_for_review=lambda: []
    )
    app.config["PARCEL_REPOSITORY"] = Mock()
    app.config["OWNERSHIP_REPOSITORY"] = Mock()
    user = active_users[Role.REGISTRAR]
    deactivate(user_repository, user.id)

    response = client.get(
        "/api/registrar/transfers", headers=bearer(app, user)
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_active_verification_officer_is_authorized(
    app, client, user_repository, active_users
):
    app.config["DOCUMENT_HASH_REPOSITORY"] = Mock(
        list_document_hashes=lambda parcel_id=None: []
    )
    user = active_users[Role.VERIFICATION_OFFICER]

    response = client.get("/api/documents", headers=bearer(app, user))

    assert response.status_code == 200
    assert response.get_json() == {"documents": []}


def test_inactive_verification_officer_is_rejected(
    app, client, user_repository, active_users
):
    app.config["DOCUMENT_HASH_REPOSITORY"] = Mock(
        list_document_hashes=lambda parcel_id=None: []
    )
    user = active_users[Role.VERIFICATION_OFFICER]
    deactivate(user_repository, user.id)

    response = client.get("/api/documents", headers=bearer(app, user))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_active_admin_is_authorized(app, client, user_repository, active_users):
    user = active_users[Role.ADMIN]

    response = client.get("/api/admin/users", headers=bearer(app, user))

    assert response.status_code == 200
    assert "users" in response.get_json()


def test_inactive_admin_is_rejected(app, client, user_repository, active_users):
    user = active_users[Role.ADMIN]
    deactivate(user_repository, user.id)

    response = client.get("/api/admin/users", headers=bearer(app, user))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


# --- Deactivation mid-session invalidates previously issued tokens -------------------


def test_token_issued_before_deactivation_stops_working(
    app, client, user_repository, active_users
):
    user = active_users[Role.CITIZEN]
    token = create_access_token(user.id, user.role, app.config["JWT_SECRET_KEY"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    deactivate(user_repository, user.id)

    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 403


def test_reactivation_restores_access(app, client, user_repository, active_users):
    user = active_users[Role.CITIZEN]
    deactivate(user_repository, user.id)
    headers = bearer(app, user)
    assert client.get("/api/auth/me", headers=headers).status_code == 403

    user_repository._users[user.id] = replace(user, is_active=True)

    assert client.get("/api/auth/me", headers=headers).status_code == 200


# --- Role authorization behavior preserved (JWT role claim still rules) -------------


def test_jwt_role_claim_still_controls_authorization(
    app, client, user_repository, active_users
):
    citizen = active_users[Role.CITIZEN]

    response = client.get("/api/admin/users", headers=bearer(app, citizen))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_deactivated_user_gets_403_not_role_evaluation(
    app, client, user_repository, active_users
):
    """Deactivated registrars are rejected even on registrar-only routes."""
    user = active_users[Role.REGISTRAR]
    deactivate(user_repository, user.id)

    response = client.get("/api/registrar/transfers", headers=bearer(app, user))

    assert response.status_code == 403


# --- Missing/deleted user behavior ---------------------------------------------------


def test_missing_user_with_valid_token_is_rejected(app, client, user_repository):
    now = datetime.now(timezone.utc)
    token = create_access_token(
        "user-that-does-not-exist", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


def test_missing_user_with_admin_token_is_rejected(app, client, user_repository):
    token = create_access_token(
        "deleted-admin", Role.ADMIN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


# --- Expired and malformed tokens -----------------------------------------------------


def test_expired_token_is_rejected_before_account_lookup(
    app, client, user_repository, active_users
):
    user = active_users[Role.CITIZEN]
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": user.id,
            "role": "CITIZEN",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "expired_token"


def test_invalid_token_is_rejected(app, client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-token"}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


def test_missing_authorization_header_is_rejected(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_authentication"


# --- Fallback: no repository configured keeps role-based behavior --------------------


def test_endpoints_work_without_configured_repository(app):
    plain_app = app
    token = create_access_token(
        "service-level-user", Role.CITIZEN, plain_app.config["JWT_SECRET_KEY"]
    )

    response = plain_app.test_client().get(
        "/api/parcels", headers={"Authorization": f"Bearer {token}"}
    )

    # Without a user store the decorator cannot verify accounts and falls back
    # to the role-based policy (the parcels endpoint then reports unavailable).
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "registry_unavailable"

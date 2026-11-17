from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import secrets

import jwt
import pytest

from app import create_app
from app.auth.api_service import AuthApiService
from app.auth.service import create_access_token, hash_password, verify_password
from app.models import Role, User
from app.persistence.errors import DatabaseUnavailableError


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
    )
    repository = Mock()
    repository.get_auth_state_by_id.return_value = (True, Role.CITIZEN)
    application.config["AUTH_USER_REPOSITORY"] = repository
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def registration_payload(**updates):
    return {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "password": "a secure password",
        "role": "CITIZEN",
        **updates,
    }


def test_register_validates_request_and_does_not_claim_persistence(client):
    client.application.config["AUTH_USER_REPOSITORY"] = None
    response = client.post("/api/auth/register", json=registration_payload())

    assert response.status_code == 503
    assert response.get_json() == {
        "error": {
            "code": "authentication_unavailable",
            "message": "Authentication service is temporarily unavailable.",
        }
    }


def test_register_rejects_missing_name(client):
    payload = registration_payload()
    payload.pop("name")

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Asha", "email": "invalid", "password": "longpassword", "role": "CITIZEN"},
        {"name": "Asha", "email": "asha@example.com", "password": "short", "role": "CITIZEN"},
        {"name": "   ", "email": "asha@example.com", "password": "longpassword", "role": "CITIZEN"},
    ],
)
def test_register_rejects_invalid_input(client, payload):
    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_register_rejects_unsupported_role(client):
    response = client.post(
        "/api/auth/register", json=registration_payload(role="OWNER")
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "unsupported_role"


@pytest.mark.parametrize(
    "role", ["REGISTRAR", "VERIFICATION_OFFICER", "ADMIN"]
)
def test_register_does_not_allow_self_assignment_of_privileged_roles(client, role):
    response = client.post(
        "/api/auth/register", json=registration_payload(role=role)
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_register_rejects_malformed_json(client):
    response = client.post(
        "/api/auth/register",
        data='{"email":',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_login_validates_request_and_returns_unavailable_without_repository(client):
    client.application.config["AUTH_USER_REPOSITORY"] = None
    response = client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "a secure password"},
    )

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "authentication_unavailable"


def test_login_rejects_missing_fields(client):
    response = client.post("/api/auth/login", json={"email": "asha@example.com"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_login_returns_invalid_credentials_when_repository_finds_no_account(app):
    repository = Mock()
    repository.get_user_by_email.return_value = None
    app.extensions["auth_api_service"] = AuthApiService(repository)

    response = app.test_client().post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "wrong password"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_credentials"
    repository.get_user_by_email.assert_called_once_with("asha@example.com")


def test_login_rejects_inactive_user_with_invalid_credentials(app):
    repository = Mock()
    repository.get_user_by_email.return_value = User(
        id="citizen-1",
        email="asha@example.com",
        password_hash=hash_password("a secure password"),
        role=Role.CITIZEN,
        name="Asha Rao",
        is_active=False,
    )
    app.extensions["auth_api_service"] = AuthApiService(repository)

    response = app.test_client().post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "a secure password"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_credentials"


def test_register_and_login_responses_never_expose_password_or_hash(app):
    repository = Mock()
    password_hash = hash_password("a secure password")
    registered_user = User(
        id="citizen-1",
        email="asha@example.com",
        password_hash=password_hash,
        role=Role.CITIZEN,
        name="Asha Rao",
    )
    repository.create_user.return_value = registered_user
    repository.get_user_by_email.return_value = registered_user
    app.extensions["auth_api_service"] = AuthApiService(repository)
    client = app.test_client()
    registration = client.post(
        "/api/auth/register", json=registration_payload()
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "a secure password"},
    )

    assert registration.status_code == 201
    assert login.status_code == 200
    assert verify_password(registered_user.password_hash, "a secure password")
    assert repository.create_user.call_args.kwargs["password_hash"] != "a secure password"
    for response in (registration, login):
        body = response.get_json()
        assert body["user"] == {
            "id": "citizen-1",
            "name": "Asha Rao",
            "email": "asha@example.com",
            "role": "CITIZEN",
        }
        assert "password" not in str(body).lower()
        assert "hash" not in str(body).lower()
        assert registered_user.password_hash not in str(body)


@pytest.mark.parametrize(
    ("authorization", "expected_code"),
    [
        (None, "missing_authentication"),
        ("Bearer malformed", "invalid_token"),
    ],
)
def test_me_rejects_missing_or_invalid_token(client, authorization, expected_code):
    headers = {} if authorization is None else {"Authorization": authorization}

    response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == expected_code


def test_me_rejects_expired_token(client, app):
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "citizen-1",
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


def test_me_returns_only_safe_identity_claims(client, app):
    token = create_access_token(
        "citizen-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body == {"user": {"id": "citizen-1", "role": "CITIZEN"}}
    assert "password" not in str(body).lower()
    assert "hash" not in str(body).lower()
    assert "secret" not in str(body).lower()


def test_me_returns_verification_officer_role(client, app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = (
        True,
        Role.VERIFICATION_OFFICER,
    )
    token = create_access_token(
        "officer-1", Role.VERIFICATION_OFFICER, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "user": {"id": "officer-1", "role": "VERIFICATION_OFFICER"}
    }


@pytest.mark.parametrize(
    "auth_state",
    [None, (False, Role.CITIZEN)],
    ids=["deleted-user", "inactive-user"],
)
def test_me_rejects_deleted_or_inactive_user_with_existing_token(
    client, app, auth_state
):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = None
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = auth_state
    token = create_access_token(
        "citizen-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


def test_me_uses_current_database_role_instead_of_token_role(client, app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = None
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = (
        True,
        Role.VERIFICATION_OFFICER,
    )
    token = create_access_token(
        "citizen-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "user": {"id": "citizen-1", "role": "VERIFICATION_OFFICER"}
    }


def test_me_fails_closed_when_user_state_lookup_fails(client, app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = (
        DatabaseUnavailableError()
    )
    token = create_access_token(
        "citizen-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "database_unavailable"

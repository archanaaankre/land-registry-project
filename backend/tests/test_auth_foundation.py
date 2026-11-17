from datetime import datetime, timedelta, timezone
import secrets
from unittest.mock import Mock

import jwt
import pytest
from flask import jsonify

from app import create_app
from app.auth.decorators import roles_required
from app.auth.errors import (
    ExpiredTokenError,
    InvalidCredentialsError,
    InvalidInputError,
    InvalidTokenError,
    UnsupportedRoleError,
)
from app.auth.service import (
    create_access_token,
    create_access_token_from_config,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.auth.validation import validate_login_input, validate_registration_input
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
    repository.get_auth_state_by_id.side_effect = lambda user_id: (
        True,
        {
            "registrar-1": Role.REGISTRAR,
            "admin-1": Role.ADMIN,
            "officer-1": Role.VERIFICATION_OFFICER,
        }.get(user_id, Role.CITIZEN),
    )
    application.config["AUTH_USER_REPOSITORY"] = repository

    @application.get("/api/test-protected")
    @roles_required(Role.REGISTRAR, Role.ADMIN)
    def protected():
        return jsonify({"user_id": "authorized"})

    @application.get("/api/test-invalid-credentials")
    def invalid_credentials():
        raise InvalidCredentialsError()

    @application.get("/api/test-invalid-input")
    def invalid_input():
        raise InvalidInputError("A valid email address is required.", field="email")

    return application


def test_password_hash_is_not_plaintext_and_verifies():
    password = "correct horse battery staple"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("scrypt:")
    assert verify_password(password_hash, password)


def test_password_verification_rejects_wrong_password():
    assert not verify_password(hash_password("first password"), "wrong password")
    assert not verify_password("malformed-hash", "first password")


def test_registration_validates_fields_email_and_role():
    result = validate_registration_input(
        {
            "email": "  Citizen@Example.com ",
            "password": "a sufficiently long password",
            "role": "CITIZEN",
        }
    )

    assert result == {
        "email": "citizen@example.com",
        "password": "a sufficiently long password",
        "role": Role.CITIZEN,
    }


@pytest.mark.parametrize("role", ["OWNER", "", None, 4])
def test_registration_rejects_unsupported_roles(role):
    with pytest.raises(UnsupportedRoleError):
        validate_registration_input(
            {"email": "citizen@example.com", "password": "longpassword", "role": role}
        )


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"email": "not-an-email", "password": "longpassword", "role": "CITIZEN"},
        {"email": "citizen@example.com", "password": "short", "role": "CITIZEN"},
        {"email": "citizen@example.com", "role": "CITIZEN"},
    ],
)
def test_registration_rejects_invalid_input(data):
    with pytest.raises(InvalidInputError):
        validate_registration_input(data)


def test_login_validates_required_fields_and_normalizes_email():
    assert validate_login_input(
        {"email": "Citizen@Example.com", "password": "password"}
    ) == {"email": "citizen@example.com", "password": "password"}

    with pytest.raises(InvalidInputError):
        validate_login_input({"email": "citizen@example.com"})


def test_user_domain_model_has_supported_role():
    user = User("user-1", "citizen@example.com", "scrypt-hash", Role.CITIZEN)
    assert user.role is Role.CITIZEN


def test_verification_officer_is_a_supported_role():
    assert Role("VERIFICATION_OFFICER") is Role.VERIFICATION_OFFICER


def test_access_token_creation_and_validation():
    secret = secrets.token_urlsafe(32)
    token = create_access_token("user-1", Role.REGISTRAR, secret)

    claims = decode_access_token(token, secret)

    assert claims["sub"] == "user-1"
    assert claims["role"] == "REGISTRAR"


def test_verification_officer_access_token_creation_and_validation():
    secret = secrets.token_urlsafe(32)
    token = create_access_token("officer-1", Role.VERIFICATION_OFFICER, secret)

    claims = decode_access_token(token, secret)

    assert claims["sub"] == "officer-1"
    assert claims["role"] == "VERIFICATION_OFFICER"


def test_configured_token_uses_environment_loaded_settings(app):
    app.config["JWT_ACCESS_TOKEN_EXPIRES_SECONDS"] = 120
    with app.app_context():
        token = create_access_token_from_config("user-1", Role.CITIZEN)

    claims = decode_access_token(token, app.config["JWT_SECRET_KEY"])
    assert claims["exp"] - claims["iat"] == 120


def test_token_validation_rejects_invalid_and_expired_tokens():
    secret = secrets.token_urlsafe(32)
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt", secret)
    with pytest.raises(InvalidTokenError):
        decode_access_token(
            create_access_token("user-1", Role.CITIZEN, secret),
            secrets.token_urlsafe(32),
        )

    expired_token = jwt.encode(
        {
            "sub": "user-1",
            "role": "CITIZEN",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=2),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        secret,
        algorithm="HS256",
    )
    with pytest.raises(ExpiredTokenError):
        decode_access_token(expired_token, secret)


def test_authorization_rejects_missing_auth_invalid_token_and_disallowed_role(app):
    client = app.test_client()
    missing = client.get("/api/test-protected")
    invalid = client.get(
        "/api/test-protected", headers={"Authorization": "Bearer invalid"}
    )
    expired_token = jwt.encode(
        {
            "sub": "user-1",
            "role": "REGISTRAR",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=2),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    expired = client.get(
        "/api/test-protected",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    citizen_token = create_access_token(
        "user-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )
    forbidden = client.get(
        "/api/test-protected",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert missing.status_code == 401
    assert missing.get_json()["error"]["code"] == "missing_authentication"
    assert invalid.status_code == 401
    assert invalid.get_json()["error"]["code"] == "invalid_token"
    assert expired.status_code == 401
    assert expired.get_json()["error"]["code"] == "expired_token"
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", [Role.REGISTRAR, Role.ADMIN])
def test_authorization_allows_configured_role(app, role):
    token = create_access_token(
        f"{role.value.lower()}-1", role, app.config["JWT_SECRET_KEY"]
    )
    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"user_id": "authorized"}


def test_verification_officer_is_not_granted_registrar_or_admin_access(app):
    token = create_access_token(
        "officer-1", Role.VERIFICATION_OFFICER, app.config["JWT_SECRET_KEY"]
    )

    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_old_token_uses_current_database_role_for_authorization(app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = (
        True,
        Role.CITIZEN,
    )
    token = create_access_token(
        "user-1", Role.ADMIN, app.config["JWT_SECRET_KEY"]
    )

    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_role_promotion_applies_to_existing_token(app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = None
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = (
        True,
        Role.REGISTRAR,
    )
    token = create_access_token(
        "user-1", Role.CITIZEN, app.config["JWT_SECRET_KEY"]
    )

    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 200
    assert response.get_json() == {"user_id": "authorized"}


@pytest.mark.parametrize(
    "auth_state",
    [None, (False, Role.REGISTRAR)],
    ids=["deleted-user", "inactive-user"],
)
def test_protected_route_rejects_deleted_or_inactive_user_with_old_token(
    app, auth_state
):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = None
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.return_value = auth_state
    token = create_access_token(
        "registrar-1", Role.REGISTRAR, app.config["JWT_SECRET_KEY"]
    )

    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


def test_protected_route_fails_closed_when_user_lookup_fails(app):
    app.config["AUTH_USER_REPOSITORY"].get_auth_state_by_id.side_effect = (
        DatabaseUnavailableError()
    )
    token = create_access_token(
        "registrar-1", Role.REGISTRAR, app.config["JWT_SECRET_KEY"]
    )

    response = app.test_client().get(
        "/api/test-protected",
        headers={"Authorization": "Bearer " + token},
    )

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "database_unavailable"


def test_authentication_error_responses_are_clean(app):
    client = app.test_client()
    response = client.get("/api/test-invalid-credentials")
    invalid_input = client.get("/api/test-invalid-input")

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Email or password is incorrect.",
        }
    }
    assert invalid_input.status_code == 400
    assert invalid_input.get_json() == {
        "error": {
            "code": "invalid_input",
            "message": "A valid email address is required.",
            "field": "email",
        }
    }

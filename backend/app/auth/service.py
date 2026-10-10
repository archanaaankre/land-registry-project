from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError as PyJWTInvalidTokenError,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.errors import (
    AuthenticationUnavailableError,
    ExpiredTokenError,
    InvalidInputError,
    InvalidTokenError,
    UnsupportedRoleError,
)
from app.models import Role


def hash_password(password):
    if not isinstance(password, str) or not password:
        raise InvalidInputError("A password is required.", field="password")
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash, password):
    if not isinstance(password_hash, str) or not isinstance(password, str):
        return False
    try:
        return check_password_hash(password_hash, password)
    except ValueError:
        return False


def _validate_token_settings(secret_key, expires_in_seconds=None):
    if not isinstance(secret_key, str) or not secret_key:
        raise AuthenticationUnavailableError()
    if expires_in_seconds is not None and (
        isinstance(expires_in_seconds, bool)
        or not isinstance(expires_in_seconds, int)
        or expires_in_seconds <= 0
    ):
        raise InvalidInputError("Token lifetime must be a positive integer.")


def create_access_token(user_id, role, secret_key, expires_in_seconds=3600):
    _validate_token_settings(secret_key, expires_in_seconds)
    if not isinstance(user_id, str) or not user_id.strip():
        raise InvalidInputError("A user identifier is required.")

    try:
        normalized_role = Role(role)
    except (TypeError, ValueError):
        raise UnsupportedRoleError() from None

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": normalized_role.value,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def create_access_token_from_config(user_id, role):
    return create_access_token(
        user_id,
        role,
        current_app.config.get("JWT_SECRET_KEY"),
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES_SECONDS"],
    )


def decode_access_token(token, secret_key):
    _validate_token_settings(secret_key)
    if not isinstance(token, str) or not token:
        raise InvalidTokenError()

    try:
        claims = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
    except ExpiredSignatureError:
        raise ExpiredTokenError() from None
    except PyJWTInvalidTokenError:
        raise InvalidTokenError() from None

    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise InvalidTokenError()
    try:
        Role(claims["role"])
    except (TypeError, ValueError):
        raise InvalidTokenError() from None
    return claims

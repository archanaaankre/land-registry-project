import re
from collections.abc import Mapping

from app.auth.errors import AuthorizationError, InvalidInputError, UnsupportedRoleError
from app.models import Role

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 128


def _require_object(data):
    if not isinstance(data, Mapping):
        raise InvalidInputError("Request body must be an object.")


def _validate_email(value):
    if not isinstance(value, str):
        raise InvalidInputError("A valid email address is required.", field="email")

    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise InvalidInputError("A valid email address is required.", field="email")
    return email


def _validate_password(value, *, registration):
    if not isinstance(value, str) or not value:
        raise InvalidInputError("A password is required.", field="password")
    if registration and not _MIN_PASSWORD_LENGTH <= len(value) <= _MAX_PASSWORD_LENGTH:
        raise InvalidInputError(
            "Password must be between 8 and 128 characters.", field="password"
        )
    if not registration and len(value) > _MAX_PASSWORD_LENGTH:
        raise InvalidInputError("Password is too long.", field="password")
    return value


def validate_registration_input(data):
    _require_object(data)
    missing = [name for name in ("email", "password", "role") if name not in data]
    if missing:
        raise InvalidInputError(
            f"Required fields are missing: {', '.join(missing)}."
        )

    role_value = data["role"]
    try:
        role = Role(role_value)
    except (TypeError, ValueError):
        raise UnsupportedRoleError() from None

    return {
        "email": _validate_email(data["email"]),
        "password": _validate_password(data["password"], registration=True),
        "role": role,
    }


def validate_api_registration_input(data):
    _require_object(data)
    if "name" not in data:
        raise InvalidInputError("Required fields are missing: name.")

    name = data["name"]
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise InvalidInputError(
            "Name must be between 1 and 100 characters.", field="name"
        )

    validated = validate_registration_input(data)
    if validated["role"] is not Role.CITIZEN:
        raise AuthorizationError("Only citizen accounts may self-register.")
    return {"name": name.strip(), **validated}


def validate_login_input(data):
    _require_object(data)
    missing = [name for name in ("email", "password") if name not in data]
    if missing:
        raise InvalidInputError(
            f"Required fields are missing: {', '.join(missing)}."
        )

    return {
        "email": _validate_email(data["email"]),
        "password": _validate_password(data["password"], registration=False),
    }

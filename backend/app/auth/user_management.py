from collections.abc import Mapping

from app.auth.errors import (
    AdminPromotionNotAllowedError,
    InvalidInputError,
    ResourceNotFoundError,
    UnsupportedRoleError,
)
from app.auth.service import hash_password
from app.auth.validation import validate_registration_input
from app.models import Role, User


class AdminUserService:
    def __init__(self, repository):
        self._repository = repository

    def create_user(self, data):
        if not isinstance(data, Mapping):
            raise InvalidInputError("Request body must be an object.")
        if "name" not in data:
            raise InvalidInputError("Required fields are missing: name.")
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise InvalidInputError(
                "Name must be between 1 and 100 characters.", field="name"
            )

        validated = validate_registration_input(data)
        if validated["role"] not in (
            Role.REGISTRAR,
            Role.VERIFICATION_OFFICER,
        ):
            raise UnsupportedRoleError(
                "Admin-created accounts must be REGISTRAR or VERIFICATION_OFFICER.",
                field="role",
            )

        user = self._repository.create_user(
            name=name.strip(),
            email=validated["email"],
            password_hash=hash_password(validated["password"]),
            role=validated["role"],
        )
        return _safe_user(user)

    def list_users(self, *, search=None, role=None, is_active=None):
        validated_role = _validate_role_filter(role)
        validated_active = _validate_active_filter(is_active)
        users = self._repository.list_users(
            search=search, role=validated_role, is_active=validated_active
        )
        return [_safe_user(user) for user in users]

    def get_user(self, user_id):
        user = self._repository.get_user_by_id(_validate_user_id(user_id))
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        return _safe_user(user)

    def update_role(self, user_id, data):
        if not isinstance(data, Mapping):
            raise InvalidInputError("Request body must be an object.")
        if "role" not in data:
            raise InvalidInputError("Required fields are missing: role.")
        try:
            role = Role(data["role"])
        except (TypeError, ValueError):
            raise UnsupportedRoleError() from None
        if role is Role.ADMIN:
            raise AdminPromotionNotAllowedError()

        user = self._repository.update_user_role(
            _validate_user_id(user_id), role
        )
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        return _safe_user(user)

    def update_status(self, user_id, data):
        if not isinstance(data, Mapping):
            raise InvalidInputError("Request body must be an object.")
        if "is_active" not in data:
            raise InvalidInputError("Required fields are missing: is_active.")
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            raise InvalidInputError(
                "is_active must be a boolean.", field="is_active"
            )

        user = self._repository.update_user_status(
            _validate_user_id(user_id), is_active
        )
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        return _safe_user(user)


def _validate_role_filter(value):
    if value is None:
        return None
    try:
        return Role(value)
    except (TypeError, ValueError):
        raise UnsupportedRoleError() from None


def _validate_active_filter(value):
    if value is None:
        return None
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise InvalidInputError(
        "is_active must be 'true' or 'false'.", field="is_active"
    )


def _validate_user_id(user_id):
    if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 128:
        raise InvalidInputError("A valid user ID is required.", field="id")
    return user_id.strip()


def _safe_user(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": Role(user.role).value,
        "is_active": user.is_active,
    }

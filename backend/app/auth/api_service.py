from typing import Protocol

from app.auth.errors import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from app.auth.service import (
    create_access_token_from_config,
    hash_password,
    verify_password,
)
from app.auth.validation import (
    validate_api_registration_input,
    validate_login_input,
)
from app.models import Role, User


class UserRepository(Protocol):
    def create_user(
        self, *, name: str, email: str, password_hash: str, role: Role
    ) -> User: ...

    def get_user_by_email(self, email: str) -> User | None: ...

    def get_user_by_id(self, user_id: str) -> User | None: ...

    def list_users(
        self,
        *,
        search: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> list[User]: ...

    def update_user_role(self, user_id: str, role: Role) -> User: ...

    def update_user_active_status(self, user_id: str, is_active: bool) -> User: ...


class AuthApiService:
    def __init__(self, repository: UserRepository | None):
        self._repository = repository

    def register(self, data):
        validated = validate_api_registration_input(data)
        repository = self._require_repository()
        user = repository.create_user(
            name=validated["name"],
            email=validated["email"],
            password_hash=hash_password(validated["password"]),
            role=validated["role"],
        )
        return self._authentication_response(user)

    def login(self, data):
        validated = validate_login_input(data)
        repository = self._require_repository()
        user = repository.get_user_by_email(validated["email"])
        if user is None or not verify_password(
            user.password_hash, validated["password"]
        ):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InvalidCredentialsError("Account is deactivated.")
        return self._authentication_response(user)

    def _require_repository(self):
        if self._repository is None:
            raise AuthenticationUnavailableError()
        return self._repository

    @staticmethod
    def _authentication_response(user):
        token = create_access_token_from_config(user.id, user.role)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": Role(user.role).value,
            },
        }

    def list_users(
        self,
        *,
        search: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> list[User]:
        repository = self._require_repository()
        return repository.list_users(search=search, role=role, is_active=is_active)

    def create_admin_user(self, data):
        """Create a privileged user (REGISTRAR or VERIFICATION_OFFICER). Admin only."""
        _require_object(data)
        if "name" not in data:
            raise InvalidInputError("Required fields are missing: name.", field="name")
        if "email" not in data:
            raise InvalidInputError("Required fields are missing: email.", field="email")
        if "password" not in data:
            raise InvalidInputError("Required fields are missing: password.", field="password")
        if "role" not in data:
            raise InvalidInputError("Required fields are missing: role.", field="role")

        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise InvalidInputError(
                "Name must be between 1 and 100 characters.", field="name"
            )

        email = data["email"]
        if not isinstance(email, str):
            raise InvalidInputError("A valid email address is required.", field="email")
        email = email.strip().lower()

        password = data["password"]
        if not isinstance(password, str) or not password:
            raise InvalidInputError("A password is required.", field="password")
        if not (8 <= len(password) <= 128):
            raise InvalidInputError(
                "Password must be between 8 and 128 characters.", field="password"
            )

        try:
            role = Role(data["role"])
        except (TypeError, ValueError):
            raise InvalidInputError("Unsupported role.", field="role") from None

        if role not in (Role.REGISTRAR, Role.VERIFICATION_OFFICER):
            raise InvalidInputError(
                "Only registrar or verification officer accounts may be created by an admin.",
                field="role",
            )

        repository = self._require_repository()
        existing = repository.get_user_by_email(email)
        if existing is not None:
            raise ResourceConflictError(
                "A user with this email already exists.", field="email"
            )

        user = repository.create_user(
            name=name.strip(),
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
            }
        }

    def update_user_role(self, user_id: str, role: Role) -> User:
        repository = self._require_repository()
        user = repository.get_user_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if user.role == role:
            return user
        updated = repository.update_user_role(user_id, role)
        return updated

    def update_user_active_status(self, user_id: str, is_active: bool) -> User:
        repository = self._require_repository()
        user = repository.get_user_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if user.is_active == is_active:
            return user
        updated = repository.update_user_active_status(user_id, is_active)
        return updated


def _require_object(data):
    if not isinstance(data, dict):
        raise InvalidInputError("Request body must be an object.")

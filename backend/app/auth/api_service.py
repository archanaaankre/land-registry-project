from typing import Protocol

from app.auth.errors import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
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

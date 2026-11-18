import logging
from typing import Protocol

from app.auth.audit import (
    EVENT_USER_ACTIVATED,
    EVENT_USER_CREATED,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    AdminAuditRecorder,
    DatabaseAdminAuditRecorder,
    build_admin_audit_event,
)
from app.auth.errors import (
    AuthenticationUnavailableError,
    AuthorizationError,
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

# Explicit allowlist of roles an admin may grant or change through the admin
# user-management API. ADMIN is deliberately excluded: the ADMIN role can
# never be assigned through these endpoints.
ADMIN_ASSIGNABLE_ROLES = frozenset(
    {Role.CITIZEN, Role.REGISTRAR, Role.VERIFICATION_OFFICER}
)

# Roles an admin may create directly (existing behavior, made explicit).
ADMIN_CREATABLE_ROLES = frozenset({Role.REGISTRAR, Role.VERIFICATION_OFFICER})


class UserRepository(Protocol):
    def create_user(
        self,
        *,
        name: str,
        email: str,
        password_hash: str,
        role: Role,
        audit_event_factory=None,
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

    def update_user_role_with_admin_guard(self, user_id: str, role: Role, audit_event_factory=None) -> User: ...

    def update_user_active_status_with_admin_guard(self, user_id: str, is_active: bool, audit_event_factory=None) -> User: ...


class AuthApiService:
    def __init__(self, repository: UserRepository | None, audit_recorder: AdminAuditRecorder | None = None):
        self._repository = repository
        # Production default: the repository persists the audit event row in
        # the same transaction as the admin mutation. Tests/development can
        # explicitly inject a different recorder.
        self._audit_recorder = (
            audit_recorder
            if audit_recorder is not None
            else DatabaseAdminAuditRecorder()
        )

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

    def create_admin_user(self, data, *, actor_id, actor_role):
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

        if role not in ADMIN_CREATABLE_ROLES:
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

        audit_factory = None
        if self._recorder_persists_to_database():
            audit_factory = self._audit_factory(
                EVENT_USER_CREATED,
                actor_id=actor_id,
                actor_role=actor_role,
                detail={"role": role.value},
            )
        user = repository.create_user(
            name=name.strip(),
            email=email,
            password_hash=hash_password(password),
            role=role,
            audit_event_factory=audit_factory,
        )
        if audit_factory is None:
            self._record_admin_audit(
                EVENT_USER_CREATED,
                actor_id=actor_id,
                actor_role=actor_role,
                target_user_id=user.id,
                detail={"role": role.value},
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

    def update_user_role(self, user_id: str, role: Role, *, actor_id, actor_role) -> User:
        repository = self._require_repository()
        try:
            role = Role(role)
        except (TypeError, ValueError):
            raise InvalidInputError("Unsupported role.", field="role") from None
        if role not in ADMIN_ASSIGNABLE_ROLES:
            raise AuthorizationError(
                "Assigning the ADMIN role is not permitted."
            )
        user = repository.get_user_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if user.role == role:
            return user
        # The last-active-admin check and the update happen atomically in the
        # guarded repository call (row locks + rollback). When the audit
        # recorder persists to the database, the audit event is inserted in
        # the same transaction; otherwise it is recorded after commit.
        audit_factory = None
        if self._recorder_persists_to_database():
            audit_factory = self._audit_factory(
                EVENT_USER_ROLE_CHANGED,
                actor_id=actor_id,
                actor_role=actor_role,
                detail={"from_role": Role(user.role).value, "to_role": role.value},
            )
        updated = repository.update_user_role_with_admin_guard(
            user_id, role, audit_event_factory=audit_factory
        )
        if audit_factory is None:
            self._record_admin_audit(
                EVENT_USER_ROLE_CHANGED,
                actor_id=actor_id,
                actor_role=actor_role,
                target_user_id=user_id,
                detail={"from_role": Role(user.role).value, "to_role": role.value},
            )
        return updated

    def update_user_active_status(self, user_id: str, is_active: bool, *, actor_id, actor_role) -> User:
        repository = self._require_repository()
        user = repository.get_user_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if user.is_active == is_active:
            return user
        if not is_active:
            if user.id == actor_id:
                raise AuthorizationError(
                    "Admins cannot deactivate their own account."
                )
        # The last-active-admin check and the update happen atomically in the
        # guarded repository call (row locks + rollback). When the audit
        # recorder persists to the database, the audit event is inserted in
        # the same transaction; otherwise it is recorded after commit.
        event_type = EVENT_USER_ACTIVATED if is_active else EVENT_USER_DEACTIVATED
        audit_factory = None
        if self._recorder_persists_to_database():
            audit_factory = self._audit_factory(
                event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                detail={"is_active": bool(is_active)},
            )
        updated = repository.update_user_active_status_with_admin_guard(
            user_id, is_active, audit_event_factory=audit_factory
        )
        if audit_factory is None:
            self._record_admin_audit(
                event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                target_user_id=user_id,
                detail={"is_active": bool(is_active)},
            )
        return updated

    def _recorder_persists_to_database(self) -> bool:
        return bool(getattr(self._audit_recorder, "persists_to_database", False))

    @staticmethod
    def _audit_factory(event_type, *, actor_id, actor_role, detail):
        """Build an event factory the repository calls with the target id.

        The repository invokes the factory inside the mutation transaction,
        so the audit row commits or rolls back with the mutation.
        """

        def build(target_user_id):
            return build_admin_audit_event(
                event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                target_user_id=target_user_id,
                detail=detail,
            )

        return build

    def _record_admin_audit(self, event_type, *, actor_id, actor_role, target_user_id, detail):
        try:
            event = build_admin_audit_event(
                event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                target_user_id=target_user_id,
                detail=detail,
            )
            self._audit_recorder.record(event)
        except Exception:
            # Audit sinks must never break the admin operation itself, and the
            # error log must not contain event payloads or secrets.
            logging.getLogger("app.audit.admin").error(
                "admin audit event could not be recorded (event_type=%s)",
                event_type,
            )


def _require_object(data):
    if not isinstance(data, dict):
        raise InvalidInputError("Request body must be an object.")

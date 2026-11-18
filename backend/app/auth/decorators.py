from functools import wraps

from flask import current_app, g, request

from app.auth.errors import (
    AuthorizationError,
    AuthenticationUnavailableError,
    InvalidTokenError,
    MissingAuthenticationError,
    UnsupportedRoleError,
)
from app.auth.service import decode_access_token
from app.models import Role


def roles_required(*allowed_roles):
    if not allowed_roles:
        raise ValueError("At least one role must be specified.")
    try:
        allowed = frozenset(Role(role) for role in allowed_roles)
    except (TypeError, ValueError):
        raise UnsupportedRoleError() from None

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            authorization = request.headers.get("Authorization")
            if authorization is None:
                raise MissingAuthenticationError()

            scheme, separator, token = authorization.partition(" ")
            if not separator or scheme.lower() != "bearer" or not token.strip():
                raise InvalidTokenError()

            secret_key = current_app.config.get("JWT_SECRET_KEY")
            if not isinstance(secret_key, str) or not secret_key:
                raise AuthenticationUnavailableError()
            claims = decode_access_token(
                token.strip(), secret_key
            )
            role = Role(claims["role"])
            if role not in allowed:
                raise AuthorizationError()
            _verify_account_is_active(claims["sub"])

            g.current_user_id = claims["sub"]
            g.current_user_role = role
            return view(*args, **kwargs)

        return wrapped

    return decorate


def _verify_account_is_active(user_id):
    """Reject requests whose account no longer exists or is deactivated.

    A valid JWT alone is not enough: the account is looked up on every
    authenticated request and must exist and be active. When no user
    repository is configured (e.g. service-level unit tests), there is
    nothing to check against and the existing role-based behavior is
    preserved. The role is intentionally NOT re-read from the database;
    authorization still uses the JWT role claim.
    """
    from app.persistence.repositories import repository_bootstrap

    repository_bootstrap(current_app)
    repository = current_app.config.get("AUTH_USER_REPOSITORY")
    if repository is None:
        return

    user = repository.get_user_by_id(user_id)
    if user is None:
        # The token references an account that no longer exists.
        raise InvalidTokenError()
    if not user.is_active:
        raise AuthorizationError("Account is deactivated.")

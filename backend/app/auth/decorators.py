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
            from app.persistence.repositories import repository_bootstrap

            repository_bootstrap(current_app)
            repository = current_app.config.get("AUTH_USER_REPOSITORY")
            if repository is None:
                # No user store configured (e.g. service-level unit tests):
                # fall back to the JWT role claim so the role-based policy
                # still applies.
                current_role = Role(claims["role"])
            else:
                current_role = _resolve_user_role(repository, claims["sub"])

            if current_role not in allowed:
                raise AuthorizationError()

            _verify_account_is_active(claims["sub"])

            g.current_user_id = claims["sub"]
            g.current_user_role = current_role
            return view(*args, **kwargs)

        return wrapped

    return decorate


def _resolve_user_role(repository, user_id):
    """Resolve the authorization role and account state from the user store.

    Prefers the repository's dedicated ``get_auth_state_by_id`` lookup when
    the repository provides one; when that lookup returns a state, the role
    comes from the database (a demoted user loses access until the token
    expires). Repositories without a usable dedicated lookup fall back to
    ``get_user_by_id``. A missing user or an inactive account always rejects.
    """
    get_auth_state = getattr(repository, "get_auth_state_by_id", None)
    if callable(get_auth_state):
        auth_state = get_auth_state(user_id)
        if auth_state is None:
            raise InvalidTokenError()
        try:
            is_active, current_role = auth_state
        except (TypeError, ValueError):
            # The dedicated lookup exists but cannot be unpacked: fall back
            # to the user record when the repository offers one.
            user = repository.get_user_by_id(user_id)
            if user is None:
                raise InvalidTokenError()
            if not user.is_active:
                raise AuthorizationError("Account is deactivated.")
            return Role(user.role)
        if not is_active:
            raise InvalidTokenError()
        try:
            return Role(current_role)
        except (TypeError, ValueError):
            raise AuthenticationUnavailableError() from None

    user = repository.get_user_by_id(user_id)
    if user is None:
        raise InvalidTokenError()
    if not user.is_active:
        raise AuthorizationError("Account is deactivated.")
    return Role(user.role)


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

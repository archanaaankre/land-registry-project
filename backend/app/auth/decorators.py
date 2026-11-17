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
            get_auth_state = getattr(repository, "get_auth_state_by_id", None)
            if not callable(get_auth_state):
                raise AuthenticationUnavailableError()

            auth_state = get_auth_state(claims["sub"])
            if auth_state is None:
                raise InvalidTokenError()
            is_active, current_role = auth_state
            if not is_active:
                raise InvalidTokenError()
            try:
                role = Role(current_role)
            except (TypeError, ValueError):
                raise AuthenticationUnavailableError() from None
            if role not in allowed:
                raise AuthorizationError()

            g.current_user_id = claims["sub"]
            g.current_user_role = role
            return view(*args, **kwargs)

        return wrapped

    return decorate

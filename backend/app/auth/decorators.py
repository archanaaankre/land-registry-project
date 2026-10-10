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

            g.current_user_id = claims["sub"]
            g.current_user_role = role
            return view(*args, **kwargs)

        return wrapped

    return decorate

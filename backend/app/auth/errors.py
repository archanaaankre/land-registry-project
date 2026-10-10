class AuthError(Exception):
    code = "authentication_error"
    message = "Authentication failed."
    status_code = 401

    def __init__(self, message=None, field=None):
        super().__init__(message or self.message)
        self.message = message or type(self).message
        self.field = field


class InvalidInputError(AuthError):
    code = "invalid_input"
    message = "Input is invalid."
    status_code = 400


class UnsupportedRoleError(AuthError):
    code = "unsupported_role"
    message = "The requested role is not supported."
    status_code = 400


class AuthorizationError(AuthError):
    code = "forbidden"
    message = "This role is not authorized."
    status_code = 403


class MissingAuthenticationError(AuthError):
    code = "missing_authentication"
    message = "Authentication is required."
    status_code = 401


class InvalidTokenError(AuthError):
    code = "invalid_token"
    message = "The authentication token is invalid."
    status_code = 401


class ExpiredTokenError(AuthError):
    code = "expired_token"
    message = "The authentication token has expired."
    status_code = 401


class InvalidCredentialsError(AuthError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."
    status_code = 401


class AuthenticationUnavailableError(AuthError):
    code = "authentication_unavailable"
    message = "Authentication service is temporarily unavailable."
    status_code = 503


class RegistryUnavailableError(AuthError):
    code = "registry_unavailable"
    message = "Registry service is temporarily unavailable."
    status_code = 503


class ResourceNotFoundError(AuthError):
    code = "not_found"
    message = "The requested resource was not found."
    status_code = 404

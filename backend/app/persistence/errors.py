from app.auth.errors import AuthError


class DatabaseUnavailableError(AuthError):
    code = "database_unavailable"
    message = "The database is temporarily unavailable."
    status_code = 503
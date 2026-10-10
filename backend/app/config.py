import os


def _get_env(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


class Config:
    SECRET_KEY = _get_env("SECRET_KEY", "generate-a-random-secret")
    JWT_SECRET_KEY = _get_env("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS = int(
        _get_env("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "3600")
    )
    SQLALCHEMY_DATABASE_URI = _get_env(
        "DATABASE_URL", "postgresql://localhost:5432/land_registry"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

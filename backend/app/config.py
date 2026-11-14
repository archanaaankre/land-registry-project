import os


def _get_env(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


_JWT_SECRET_PLACEHOLDERS = {
    "change-me",
    "changeme",
    "development",
    "generate-a-random-secret",
    "jwt-secret",
    "placeholder",
    "secret",
    "test-jwt",
    "test-only",
    "test-secret",
    "your-jwt-secret",
    "your-secret-key",
}
_JWT_SECRET_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "default",
    "development",
    "devsecret",
    "example",
    "generate-a-random-secret",
    "insecure",
    "letmein",
    "password",
    "placeholder",
    "replace-me",
    "replace-this",
    "secret",
    "supersecret",
    "testjwt",
    "testonly",
    "testsecret",
    "your-jwt",
    "your-secret",
)


def _has_repeated_pattern(value):
    if len(value) < 2:
        return False

    prefix_lengths = [0] * len(value)
    matched_length = 0
    for index in range(1, len(value)):
        while matched_length and value[index] != value[matched_length]:
            matched_length = prefix_lengths[matched_length - 1]
        if value[index] == value[matched_length]:
            matched_length += 1
            prefix_lengths[index] = matched_length

    pattern_length = len(value) - prefix_lengths[-1]
    return pattern_length < len(value) and len(value) % pattern_length == 0


def _has_sequential_run(value):
    run_length = 1
    direction = 0

    for previous, current in zip(value, value[1:]):
        if (
            previous.isascii()
            and current.isascii()
            and previous.isalnum()
            and current.isalnum()
        ):
            difference = ord(current.lower()) - ord(previous.lower())
            if abs(difference) == 1:
                if difference == direction:
                    run_length += 1
                else:
                    direction = difference
                    run_length = 2
                if run_length >= 8:
                    return True
            else:
                direction = 0
                run_length = 1
        else:
            direction = 0
            run_length = 1

    return False


def validate_jwt_secret(secret):
    message = (
        "JWT_SECRET_KEY must be a cryptographically random secret of at least "
        "32 bytes; common placeholders and trivial patterns are not allowed."
    )
    if not isinstance(secret, str):
        raise ValueError(message)

    normalized_secret = secret.strip()
    compact_secret = "".join(
        character for character in normalized_secret.lower() if character.isalnum()
    )
    if (
        len(normalized_secret.encode("utf-8")) < 32
        or not normalized_secret
        or compact_secret in _JWT_SECRET_PLACEHOLDERS
        or any(
            marker.replace("-", "") in compact_secret
            for marker in _JWT_SECRET_PLACEHOLDER_MARKERS
        )
        or len(set(compact_secret)) < 8
        or _has_repeated_pattern(compact_secret)
        or _has_sequential_run(normalized_secret)
    ):
        raise ValueError(message)


class Config:
    SECRET_KEY = _get_env("SECRET_KEY", "generate-a-random-secret")
    JWT_SECRET_KEY = _get_env("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS = int(
        _get_env("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "3600")
    )
    SQLALCHEMY_DATABASE_URI = _get_env(
        "DATABASE_URL", "postgresql://localhost:5432/land_registry"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

import secrets

import pytest

from app import create_app
from app.config import validate_jwt_secret


VALID_TEST_SECRET = secrets.token_hex(32)


@pytest.mark.parametrize(
    "secret",
    [
        None,
        "",
        "super-secret-key-that-is-at-least-32-bytes-long",
        "this-is-a-default-development-key-1234567890",
        "generate-a-random-secret-value-that-is-long-enough",
        "test-only-jwt-secret-that-is-long-enough",
        "a" * 32,
        "abc123" * 6,
        "aZ9kM2pQ1" * 4,
        "0123456789abcdef" * 2,
        "abcdefghijklmnopqrstuvwxyz012345",
        "12345678901234567890123456789012",
        "\u0130abcdefghijklmnopqrstuvwxyz012345",
        "change-me",
        "secret",
        "too-short",
    ],
)
def test_validate_jwt_secret_rejects_placeholders_and_trivial_secrets(secret):
    with pytest.raises(ValueError, match="cryptographically random"):
        validate_jwt_secret(secret)


@pytest.mark.parametrize("_", range(100))
def test_validate_jwt_secret_accepts_valid_random_32_byte_secrets(_):
    validate_jwt_secret(secrets.token_hex(32))


def test_invalid_secret_error_does_not_expose_configured_value():
    placeholder = "this-is-a-default-development-key-1234567890"

    with pytest.raises(ValueError) as error:
        validate_jwt_secret(placeholder)

    assert placeholder not in str(error.value)


def test_create_app_starts_with_explicit_valid_test_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setattr("app.load_dotenv", lambda *args, **kwargs: False)

    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET_KEY": VALID_TEST_SECRET,
        }
    )

    assert app.config["JWT_SECRET_KEY"] is VALID_TEST_SECRET


@pytest.mark.parametrize("secret", [None, "", "generate-a-random-secret"])
def test_create_app_refuses_missing_empty_or_placeholder_secret(secret):
    with pytest.raises(ValueError, match="cryptographically random"):
        create_app({"JWT_SECRET_KEY": secret})

"""Input validation for document integrity operations."""

import re

from app.auth.errors import InvalidInputError

_MAX_DOCUMENT_NAME_LENGTH = 200
_DOCUMENT_NAME_PATTERN = re.compile(r"^[\w\s\-_\.]+$")


def validate_document_name(name: str) -> str:
    """Validate and normalize a document name.

    Args:
        name: The document name to validate.

    Returns:
        The stripped document name.

    Raises:
        InvalidInputError: If the name is missing, too long, or contains
            invalid characters.
    """
    if not isinstance(name, str) or not name.strip():
        raise InvalidInputError(
            "A document name is required.", field="document_name"
        )

    name = name.strip()

    if len(name) > _MAX_DOCUMENT_NAME_LENGTH:
        raise InvalidInputError(
            f"Document name must not exceed {_MAX_DOCUMENT_NAME_LENGTH} characters.",
            field="document_name",
        )

    if not _DOCUMENT_NAME_PATTERN.match(name):
        raise InvalidInputError(
            "Document name may only contain letters, numbers, spaces, "
            "hyphens, underscores, and periods.",
            field="document_name",
        )

    return name

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.auth.errors import InvalidInputError
from app.models import AreaUnit, OwnershipStatus, ParcelStatus

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_CADASTRAL_NUMBER_LENGTH = 100
_MAX_LOCATION_LENGTH = 500


def _required_text(data, field, max_length=100):
    value = data.get(field)
    if not isinstance(value, str):
        raise InvalidInputError(f"{field} is required.", field=field)

    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise InvalidInputError(
            f"{field} must be between 1 and {max_length} characters.",
            field=field,
        )
    return normalized


def _identifier(data, field):
    return validate_identifier(data.get(field), field)


def validate_identifier(value, field):
    value = value.strip() if isinstance(value, str) else value
    if not isinstance(value, str) or not value or len(value) > 64:
        raise InvalidInputError(f"{field} is required.", field=field)
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise InvalidInputError(f"{field} is invalid.", field=field)
    return value


def _require_fields(data, fields):
    if not isinstance(data, Mapping):
        raise InvalidInputError("Request data must be an object.")
    missing = [field for field in fields if field not in data]
    if missing:
        raise InvalidInputError(
            f"Required fields are missing: {', '.join(missing)}."
        )
    unknown = set(data) - set(fields)
    if unknown:
        raise InvalidInputError("Request data contains unsupported fields.")


def _enum_value(enum_type, value, field):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise InvalidInputError(f"{field} is not supported.", field=field) from None


def _positive_decimal(data, field, maximum=None):
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InvalidInputError(f"{field} must be a number.", field=field)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise InvalidInputError(f"{field} must be a number.", field=field) from None

    if not number.is_finite() or number <= 0:
        raise InvalidInputError(f"{field} must be positive.", field=field)
    if maximum is not None and number > maximum:
        raise InvalidInputError(f"{field} must not exceed {maximum}.", field=field)
    return number


def validate_parcel_data(data):
    fields = (
        "parcel_id",
        "cadastral_number",
        "location",
        "area",
        "area_unit",
        "status",
    )
    _require_fields(data, fields)
    return {
        "parcel_id": _identifier(data, "parcel_id"),
        "cadastral_number": _required_text(
            data, "cadastral_number", _MAX_CADASTRAL_NUMBER_LENGTH
        ),
        "location": _required_text(data, "location", _MAX_LOCATION_LENGTH),
        "area": _positive_decimal(data, "area"),
        "area_unit": _enum_value(AreaUnit, data["area_unit"], "area_unit"),
        "status": _enum_value(ParcelStatus, data["status"], "status"),
    }


def validate_ownership_data(data):
    fields = ("ownership_id", "parcel_id", "owner_id", "share", "status")
    _require_fields(data, fields)
    return {
        "ownership_id": _identifier(data, "ownership_id"),
        "parcel_id": _identifier(data, "parcel_id"),
        "owner_id": _identifier(data, "owner_id"),
        "share": _positive_decimal(data, "share", maximum=Decimal("100")),
        "status": _enum_value(OwnershipStatus, data["status"], "status"),
    }

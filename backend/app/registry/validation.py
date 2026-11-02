import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.auth.errors import InvalidInputError
from app.models import AreaUnit, OwnershipStatus, ParcelStatus

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_CADASTRAL_NUMBER_LENGTH = 100
_CADASTRAL_EDGE_WHITESPACE = " \t\n\r\v\f"
_MAX_LOCATION_LENGTH = 500
_MAX_PARCEL_AREA = Decimal("99999999999999.999999")


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


def normalize_cadastral_number(value):
    return value.strip(_CADASTRAL_EDGE_WHITESPACE).upper()


def _cadastral_number(data):
    value = data.get("cadastral_number")
    if not isinstance(value, str):
        raise InvalidInputError(
            "cadastral_number is required.", field="cadastral_number"
        )
    normalized = normalize_cadastral_number(value)
    if not normalized:
        raise InvalidInputError(
            "cadastral_number must contain non-whitespace characters.",
            field="cadastral_number",
        )
    if len(normalized) > _MAX_CADASTRAL_NUMBER_LENGTH:
        raise InvalidInputError(
            "cadastral_number must not exceed "
            f"{_MAX_CADASTRAL_NUMBER_LENGTH} characters.",
            field="cadastral_number",
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


def _parcel_area(data):
    number = _positive_decimal(data, "area", maximum=_MAX_PARCEL_AREA)
    if number.normalize().as_tuple().exponent < -6:
        raise InvalidInputError(
            "area must have no more than 6 decimal places.", field="area"
        )
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
        "cadastral_number": _cadastral_number(data),
        "location": _required_text(data, "location", _MAX_LOCATION_LENGTH),
        "area": _parcel_area(data),
        "area_unit": _enum_value(AreaUnit, data["area_unit"], "area_unit"),
        "status": _enum_value(ParcelStatus, data["status"], "status"),
    }


def validate_parcel_update_data(data):
    fields = {"cadastral_number", "location", "area", "area_unit"}
    if not isinstance(data, Mapping):
        raise InvalidInputError("Request data must be an object.")
    if not data:
        raise InvalidInputError("At least one parcel field must be provided.")
    if set(data) - fields:
        raise InvalidInputError("Request data contains unsupported fields.")

    validated = {}
    if "cadastral_number" in data:
        validated["cadastral_number"] = _cadastral_number(data)
    if "location" in data:
        validated["location"] = _required_text(
            data, "location", _MAX_LOCATION_LENGTH
        )
    if "area" in data:
        validated["area"] = _parcel_area(data)
    if "area_unit" in data:
        validated["area_unit"] = _enum_value(AreaUnit, data["area_unit"], "area_unit")
    return validated


def validate_parcel_search_data(data):
    if not isinstance(data, Mapping):
        raise InvalidInputError("Search parameters are invalid.")

    allowed_fields = {
        "search",
        "cadastral_number",
        "location",
        "status",
        "page",
        "page_size",
    }
    if set(data) - allowed_fields:
        raise InvalidInputError("Search parameters contain unsupported fields.")

    filters = {}
    for field, max_length in (
        ("search", _MAX_LOCATION_LENGTH),
        ("cadastral_number", _MAX_CADASTRAL_NUMBER_LENGTH),
        ("location", _MAX_LOCATION_LENGTH),
    ):
        value = data.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise InvalidInputError(f"{field} must be text.", field=field)
            normalized = (
                normalize_cadastral_number(value)
                if field == "cadastral_number"
                else value.strip()
            )
            if len(normalized) > max_length:
                raise InvalidInputError(
                    f"{field} must not exceed {max_length} characters.",
                    field=field,
                )
            if normalized:
                filters[field] = normalized

    if data.get("status") is not None:
        filters["status"] = _enum_value(ParcelStatus, data["status"], "status")

    pagination_requested = "page" in data or "page_size" in data
    if pagination_requested:
        filters["page"] = _positive_integer(data.get("page", "1"), "page")
        filters["page_size"] = _positive_integer(
            data.get("page_size", "50"), "page_size", maximum=100
        )
    return filters, pagination_requested


def _positive_integer(value, field, maximum=None):
    if isinstance(value, bool):
        raise InvalidInputError(f"{field} must be a positive integer.", field=field)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InvalidInputError(
            f"{field} must be a positive integer.", field=field
        ) from None
    if str(number) != str(value).strip() or number < 1:
        raise InvalidInputError(f"{field} must be a positive integer.", field=field)
    if maximum is not None and number > maximum:
        raise InvalidInputError(
            f"{field} must not exceed {maximum}.", field=field
        )
    return number


def validate_ownership_data(data):
    fields = ("ownership_id", "parcel_id", "owner_id", "share", "status")
    _require_fields(data, fields)
    share = _positive_decimal(data, "share", maximum=Decimal("100"))
    if share.normalize().as_tuple().exponent < -6:
        raise InvalidInputError(
            "share must have no more than 6 decimal places.", field="share"
        )
    return {
        "ownership_id": _identifier(data, "ownership_id"),
        "parcel_id": _identifier(data, "parcel_id"),
        "owner_id": _identifier(data, "owner_id"),
        "share": share,
        "status": _enum_value(OwnershipStatus, data["status"], "status"),
    }

import re
from collections.abc import Mapping

from app.auth.errors import InvalidInputError
from app.models import Role
from app.registry.validation import validate_identifier

_BUYER_REFERENCE_MAX_LENGTH = 254
_REASON_MAX_LENGTH = 500


def _require_object(data):
    if not isinstance(data, Mapping):
        raise InvalidInputError("Request body must be an object.")


def validate_transfer_submission(data):
    _require_object(data)
    if "parcel_id" not in data:
        raise InvalidInputError("Required fields are missing: parcel_id.", field="parcel_id")
    if "buyer_reference" not in data:
        raise InvalidInputError(
            "Required fields are missing: buyer_reference.", field="buyer_reference"
        )
    if set(data) - {"parcel_id", "buyer_reference"}:
        raise InvalidInputError("Request data contains unsupported fields.")

    buyer_reference = data["buyer_reference"]
    if not isinstance(buyer_reference, str):
        raise InvalidInputError("buyer_reference is required.", field="buyer_reference")
    buyer_reference = buyer_reference.strip()
    if not buyer_reference or len(buyer_reference) > _BUYER_REFERENCE_MAX_LENGTH:
        raise InvalidInputError(
            "buyer_reference must be between 1 and 254 characters.",
            field="buyer_reference",
        )
    if "@" in buyer_reference:
        buyer_reference = buyer_reference.lower()

    return {
        "parcel_id": validate_identifier(data["parcel_id"], "parcel_id"),
        "buyer_reference": buyer_reference,
    }


def validate_request_id(value):
    return validate_identifier(value, "request_id")


def validate_role_name(value):
    try:
        return Role(value)
    except (TypeError, ValueError):
        raise InvalidInputError("role must be supported.", field="role") from None


def validate_review_decision(data, *, require_reason=False):
    _require_object(data)
    allowed_fields = {"reason"}
    if set(data) - allowed_fields:
        raise InvalidInputError("Request data contains unsupported fields.")

    reason = None
    if "reason" in data:
        if data["reason"] is None:
            if require_reason:
                raise InvalidInputError(
                    "reason is required when rejecting a transfer.",
                    field="reason",
                )
        elif not isinstance(data["reason"], str):
            raise InvalidInputError("reason must be text.", field="reason")
        else:
            reason = data["reason"].strip() or None

    if require_reason and not reason:
        raise InvalidInputError(
            "reason is required when rejecting a transfer.",
            field="reason",
        )
    if reason and len(reason) > _REASON_MAX_LENGTH:
        raise InvalidInputError(
            f"reason must not exceed {_REASON_MAX_LENGTH} characters.",
            field="reason",
        )
    return {"reason": reason}
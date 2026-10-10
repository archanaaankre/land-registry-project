from decimal import Decimal

import pytest

from app.auth.errors import InvalidInputError, RegistryUnavailableError
from app.models import AreaUnit, OwnershipStatus, ParcelStatus
from app.registry.services import OwnershipService, ParcelService
from app.registry.validation import validate_ownership_data, validate_parcel_data


def parcel_data(**updates):
    return {
        "parcel_id": "parcel-001",
        "cadastral_number": "CAD-2026-001",
        "location": "Ward 4, Sample District",
        "area": 1250.5,
        "area_unit": "SQ_METERS",
        "status": "ACTIVE",
        **updates,
    }


def ownership_data(**updates):
    return {
        "ownership_id": "ownership-001",
        "parcel_id": "parcel-001",
        "owner_id": "citizen-001",
        "share": 50,
        "status": "ACTIVE",
        **updates,
    }


def test_valid_parcel_data_is_normalized_and_uses_controlled_values():
    result = validate_parcel_data(parcel_data())

    assert result["parcel_id"] == "parcel-001"
    assert result["area"] == Decimal("1250.5")
    assert result["area_unit"] is AreaUnit.SQ_METERS
    assert result["status"] is ParcelStatus.ACTIVE


@pytest.mark.parametrize(
    "updates",
    [
        {"parcel_id": ""},
        {"parcel_id": "not valid!"},
        {"cadastral_number": ""},
        {"location": ""},
        {"area": 0},
        {"area": -1},
        {"area": float("inf")},
        {"area": True},
        {"area_unit": "SQUARE_FEET"},
        {"status": "PENDING_APPROVAL"},
    ],
)
def test_invalid_parcel_data_is_rejected(updates):
    with pytest.raises(InvalidInputError):
        validate_parcel_data(parcel_data(**updates))


@pytest.mark.parametrize(
    "field",
    ["parcel_id", "cadastral_number", "location", "area", "area_unit", "status"],
)
def test_missing_parcel_fields_are_rejected(field):
    data = parcel_data()
    data.pop(field)

    with pytest.raises(InvalidInputError):
        validate_parcel_data(data)


def test_valid_ownership_data_is_normalized():
    result = validate_ownership_data(ownership_data())

    assert result["ownership_id"] == "ownership-001"
    assert result["parcel_id"] == "parcel-001"
    assert result["owner_id"] == "citizen-001"
    assert result["share"] == Decimal("50")
    assert result["status"] is OwnershipStatus.ACTIVE


@pytest.mark.parametrize(
    "updates",
    [
        {"ownership_id": ""},
        {"parcel_id": ""},
        {"owner_id": ""},
        {"share": 0},
        {"share": -1},
        {"share": 100.01},
        {"share": float("nan")},
        {"status": "TRANSFER_PENDING"},
    ],
)
def test_invalid_ownership_data_is_rejected(updates):
    with pytest.raises(InvalidInputError):
        validate_ownership_data(ownership_data(**updates))


@pytest.mark.parametrize(
    "field", ["ownership_id", "parcel_id", "owner_id", "share", "status"]
)
def test_missing_ownership_fields_are_rejected(field):
    data = ownership_data()
    data.pop(field)

    with pytest.raises(InvalidInputError):
        validate_ownership_data(data)


def test_domain_services_validate_before_requiring_repository():
    with pytest.raises(InvalidInputError):
        ParcelService(None).create_parcel(parcel_data(area=0))
    with pytest.raises(InvalidInputError):
        OwnershipService(None, None).create_ownership(ownership_data(share=101))


def test_valid_operations_report_repository_unavailable_without_persistence():
    with pytest.raises(RegistryUnavailableError):
        ParcelService(None).create_parcel(parcel_data())
    with pytest.raises(RegistryUnavailableError):
        OwnershipService(None, None).create_ownership(ownership_data())

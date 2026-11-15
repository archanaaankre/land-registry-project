from decimal import Decimal

import pytest

from app.auth.errors import (
    InvalidInputError,
    RegistryUnavailableError,
    ResourceConflictError,
)
from app.models import (
    AreaUnit,
    Ownership,
    OwnershipStatus,
    ParcelStatus,
    utc_now,
)
from app.registry.services import OwnershipService, ParcelService
from app.registry.validation import (
    validate_ownership_data,
    validate_parcel_data,
    validate_parcel_search_data,
    validate_parcel_update_data,
)


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


def test_cadastral_number_is_normalized_for_registration_and_updates():
    assert validate_parcel_data(
        parcel_data(cadastral_number="  cad-2026-001  ")
    )["cadastral_number"] == "CAD-2026-001"
    assert validate_parcel_update_data(
        {"cadastral_number": "  cad-2026-002  "}
    ) == {"cadastral_number": "CAD-2026-002"}


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"status": "DISPUTED"},
        {"owner_id": "citizen-2"},
        {"area": 0},
        {"cadastral_number": " "},
    ],
)
def test_parcel_update_rejects_empty_or_unsupported_data(data):
    with pytest.raises(InvalidInputError):
        validate_parcel_update_data(data)


def test_parcel_search_validation_supports_filters_and_optional_pagination():
    filters, pagination_requested = validate_parcel_search_data(
        {
            "search": "ward",
            "cadastral_number": " cad-1 ",
            "status": "ACTIVE",
            "page": "2",
            "page_size": "10",
        }
    )

    assert filters == {
        "search": "ward",
        "cadastral_number": "CAD-1",
        "status": ParcelStatus.ACTIVE,
        "page": 2,
        "page_size": 10,
    }
    assert pagination_requested


@pytest.mark.parametrize(
    "data",
    [
        {"status": "UNKNOWN"},
        {"page": "0"},
        {"page": "-1"},
        {"page": "one"},
        {"page_size": "101"},
        {"unknown": "value"},
    ],
)
def test_invalid_parcel_search_parameters_are_rejected(data):
    with pytest.raises(InvalidInputError):
        validate_parcel_search_data(data)


@pytest.mark.parametrize(
    "updates",
    [
        {"parcel_id": ""},
        {"parcel_id": "not valid!"},
        {"cadastral_number": ""},
        {"location": ""},
        {"area": 0},
        {"area": -1},
        {"area": 1.1234567},
        {"area": 100000000000000},
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
        {"share": Decimal("1.0000001")},
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


class _OwnershipRepository:
    def __init__(self, records=()):
        self.records = list(records)
        self.created = []

    def list_for_parcel(self, parcel_id):
        return [
            record for record in self.records if record.parcel_id == parcel_id
        ]

    def create_ownership(self, ownership):
        self.created.append(ownership)
        return ownership


class _ParcelRepository:
    def find_by_id(self, parcel_id):
        return object() if parcel_id == "parcel-001" else None


def _ownership_record(ownership_id, owner_id, share, status):
    now = utc_now()
    return Ownership(
        ownership_id=ownership_id,
        parcel_id="parcel-001",
        owner_id=owner_id,
        share=Decimal(share),
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_ownership_service_allows_exact_aggregate_and_multiple_owners():
    repository = _OwnershipRepository(
        [
            _ownership_record(
                "ownership-1",
                "citizen-1",
                "33.333333",
                OwnershipStatus.ACTIVE,
            )
        ]
    )
    service = OwnershipService(repository, _ParcelRepository())

    created = service.create_ownership(
        ownership_data(
            ownership_id="ownership-2",
            owner_id="citizen-2",
            share=Decimal("66.666667"),
        )
    )

    assert created.share == Decimal("66.666667")
    assert len(repository.created) == 1


def test_ownership_service_rejects_overallocation_without_creating_record():
    repository = _OwnershipRepository(
        [_ownership_record("ownership-1", "citizen-1", "80", OwnershipStatus.ACTIVE)]
    )
    service = OwnershipService(repository, _ParcelRepository())

    with pytest.raises(ResourceConflictError, match="cannot exceed 100%"):
        service.create_ownership(
            ownership_data(ownership_id="ownership-2", owner_id="citizen-2", share=21)
        )

    assert repository.created == []


def test_ownership_service_rejects_duplicate_active_owner():
    repository = _OwnershipRepository(
        [_ownership_record("ownership-1", "citizen-001", "40", OwnershipStatus.ACTIVE)]
    )
    service = OwnershipService(repository, _ParcelRepository())

    with pytest.raises(ResourceConflictError, match="already has an active"):
        service.create_ownership(ownership_data(share=20))

    assert repository.created == []


def test_ownership_service_current_and_history_are_status_based():
    repository = _OwnershipRepository(
        [
            _ownership_record("ownership-1", "citizen-1", "100", OwnershipStatus.INACTIVE),
            _ownership_record("ownership-2", "citizen-2", "100", OwnershipStatus.ACTIVE),
            _ownership_record("ownership-3", "citizen-3", "100", OwnershipStatus.DISPUTED),
        ]
    )
    service = OwnershipService(repository, _ParcelRepository())

    assert [
        item.ownership_id
        for item in service.list_current_for_parcel("parcel-001")
    ] == ["ownership-2"]
    assert [
        item.ownership_id
        for item in service.list_history_for_parcel("parcel-001")
    ] == ["ownership-1", "ownership-3"]

from decimal import Decimal

from app.auth.errors import (
    InvalidInputError,
    RegistryUnavailableError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from app.models import Ownership, OwnershipStatus, Parcel, ParcelStatus, utc_now
from app.registry.repositories import OwnershipRepository, ParcelRepository
from app.registry.validation import (
    validate_identifier,
    validate_ownership_data,
    validate_parcel_data,
    validate_parcel_update_data,
)

_ALLOWED_PARCEL_STATUS_TRANSITIONS = {
    ParcelStatus.ACTIVE: {ParcelStatus.INACTIVE, ParcelStatus.DISPUTED},
    ParcelStatus.INACTIVE: {ParcelStatus.ACTIVE, ParcelStatus.DISPUTED},
    ParcelStatus.DISPUTED: {ParcelStatus.ACTIVE, ParcelStatus.INACTIVE},
}


class ParcelService:
    def __init__(self, repository: ParcelRepository | None):
        self._repository = repository

    def list_parcels(self):
        return self._require_repository().list_parcels()

    def search_parcels(self, **filters):
        return self._require_repository().search_parcels(**filters)

    def get_parcel(self, parcel_id):
        parcel_id = validate_identifier(parcel_id, "parcel_id")
        parcel = self._require_repository().find_by_id(parcel_id)
        if parcel is None:
            raise ResourceNotFoundError("Parcel was not found.")
        return parcel

    def create_parcel(self, data):
        validated = validate_parcel_data(data)
        now = utc_now()
        parcel = Parcel(**validated, created_at=now, updated_at=now)
        return self._require_repository().create_parcel(parcel)

    def update_parcel(self, parcel_id, data):
        parcel_id = validate_identifier(parcel_id, "parcel_id")
        updates = validate_parcel_update_data(data)
        repository = self._require_repository()
        if repository.find_by_id(parcel_id) is None:
            raise ResourceNotFoundError("Parcel was not found.")
        updated = repository.update_parcel(
            parcel_id, updates, updated_at=utc_now()
        )
        if updated is None:
            raise ResourceNotFoundError("Parcel was not found.")
        return updated

    def update_status(self, parcel_id, status):
        parcel_id = validate_identifier(parcel_id, "parcel_id")
        if not isinstance(status, str):
            raise InvalidInputError("status is not supported.", field="status")
        try:
            target_status = ParcelStatus(status)
        except ValueError:
            raise InvalidInputError(
                "status is not supported.", field="status"
            ) from None

        repository = self._require_repository()
        parcel = repository.find_by_id(parcel_id)
        if parcel is None:
            raise ResourceNotFoundError("Parcel was not found.")
        if target_status not in _ALLOWED_PARCEL_STATUS_TRANSITIONS[parcel.status]:
            raise ResourceConflictError(
                f"Parcel status cannot move from {parcel.status.value} "
                f"to {target_status.value}."
            )
        updated = repository.update_parcel_status(
            parcel_id,
            expected_status=parcel.status,
            status=target_status,
            updated_at=utc_now(),
        )
        if updated is None:
            raise ResourceNotFoundError("Parcel was not found.")
        return updated

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository


class OwnershipService:
    def __init__(
        self,
        repository: OwnershipRepository | None,
        parcel_repository: ParcelRepository | None,
    ):
        self._repository = repository
        self._parcel_repository = parcel_repository

    def list_for_parcel(self, parcel_id):
        parcel_id = validate_identifier(parcel_id, "parcel_id")
        parcel_repository = self._require_parcel_repository()
        if parcel_repository.find_by_id(parcel_id) is None:
            raise ResourceNotFoundError("Parcel was not found.")
        return self._require_repository().list_for_parcel(parcel_id)

    def list_current_for_parcel(self, parcel_id):
        return [
            record
            for record in self.list_for_parcel(parcel_id)
            if record.status == OwnershipStatus.ACTIVE
        ]

    def list_history_for_parcel(self, parcel_id):
        return [
            record
            for record in self.list_for_parcel(parcel_id)
            if record.status != OwnershipStatus.ACTIVE
        ]

    def get_ownership(self, ownership_id):
        ownership_id = validate_identifier(ownership_id, "ownership_id")
        ownership = self._require_repository().find_by_id(ownership_id)
        if ownership is None:
            raise ResourceNotFoundError("Ownership record was not found.")
        return ownership

    def create_ownership(self, data):
        validated = validate_ownership_data(data)
        repository = self._require_repository()
        parcel_repository = self._require_parcel_repository()
        if parcel_repository.find_by_id(validated["parcel_id"]) is None:
            raise ResourceNotFoundError("Parcel was not found.")

        existing_records = repository.list_for_parcel(validated["parcel_id"])
        if validated["status"] == OwnershipStatus.ACTIVE:
            active_records = [
                record
                for record in existing_records
                if record.status == OwnershipStatus.ACTIVE
            ]
            if any(
                record.owner_id == validated["owner_id"]
                for record in active_records
            ):
                raise ResourceConflictError(
                    "This owner already has an active ownership record for the parcel."
                )
            total_share = sum(
                (record.share for record in active_records), Decimal("0")
            )
            if total_share + validated["share"] > Decimal("100"):
                raise ResourceConflictError(
                    "Active ownership shares for a parcel cannot exceed 100%."
                )

        now = utc_now()
        ownership = Ownership(**validated, created_at=now, updated_at=now)
        return repository.create_ownership(ownership)

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    def _require_parcel_repository(self):
        if self._parcel_repository is None:
            raise RegistryUnavailableError()
        return self._parcel_repository

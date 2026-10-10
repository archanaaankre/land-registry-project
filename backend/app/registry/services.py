from app.auth.errors import RegistryUnavailableError, ResourceNotFoundError
from app.models import Ownership, Parcel, utc_now
from app.registry.repositories import OwnershipRepository, ParcelRepository
from app.registry.validation import (
    validate_identifier,
    validate_ownership_data,
    validate_parcel_data,
)


class ParcelService:
    def __init__(self, repository: ParcelRepository | None):
        self._repository = repository

    def list_parcels(self):
        return self._require_repository().list_parcels()

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

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository


class OwnershipService:
    """Active shares per parcel should total at most 100%; that check is deferred."""

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

    def get_ownership(self, ownership_id):
        ownership_id = validate_identifier(ownership_id, "ownership_id")
        ownership = self._require_repository().find_by_id(ownership_id)
        if ownership is None:
            raise ResourceNotFoundError("Ownership record was not found.")
        return ownership

    def create_ownership(self, data):
        validated = validate_ownership_data(data)
        parcel_repository = self._require_parcel_repository()
        if parcel_repository.find_by_id(validated["parcel_id"]) is None:
            raise ResourceNotFoundError("Parcel was not found.")

        now = utc_now()
        ownership = Ownership(**validated, created_at=now, updated_at=now)
        return self._require_repository().create_ownership(ownership)

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    def _require_parcel_repository(self):
        if self._parcel_repository is None:
            raise RegistryUnavailableError()
        return self._parcel_repository

from typing import Protocol

from app.models import Ownership, Parcel, ParcelStatus


class ParcelRepository(Protocol):
    def find_by_id(self, parcel_id: str) -> Parcel | None: ...

    def list_parcels(self) -> list[Parcel]: ...

    def search_parcels(
        self,
        *,
        search: str | None = None,
        cadastral_number: str | None = None,
        location: str | None = None,
        status: ParcelStatus | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[list[Parcel], int]: ...

    def create_parcel(self, parcel: Parcel) -> Parcel: ...

    def update_parcel(self, parcel_id: str, updates: dict, *, updated_at) -> Parcel: ...

    def update_parcel_status(
        self, parcel_id, *, expected_status, status, updated_at
    ) -> Parcel: ...


class OwnershipRepository(Protocol):
    def find_by_id(self, ownership_id: str) -> Ownership | None: ...

    def list_for_parcel(self, parcel_id: str) -> list[Ownership]: ...

    def create_ownership(self, ownership: Ownership) -> Ownership: ...

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Role(str, Enum):
    CITIZEN = "CITIZEN"
    REGISTRAR = "REGISTRAR"
    ADMIN = "ADMIN"


class ParcelStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISPUTED = "DISPUTED"


class AreaUnit(str, Enum):
    SQ_METERS = "SQ_METERS"
    HECTARES = "HECTARES"
    ACRES = "ACRES"


class OwnershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISPUTED = "DISPUTED"


def utc_now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class User:
    id: str
    email: str
    password_hash: str
    role: Role
    name: str = ""


@dataclass(frozen=True)
class Parcel:
    parcel_id: str
    cadastral_number: str
    location: str
    area: Decimal
    area_unit: AreaUnit
    status: ParcelStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Ownership:
    ownership_id: str
    parcel_id: str
    owner_id: str
    share: Decimal
    status: OwnershipStatus
    created_at: datetime
    updated_at: datetime

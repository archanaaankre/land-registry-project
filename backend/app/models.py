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


class TransferStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    BLOCKCHAIN_PENDING = "BLOCKCHAIN_PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BlockchainSubmissionStatus(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class TransferRequest:
    request_id: str
    parcel_id: str
    seller_id: str
    buyer_reference: str
    status: TransferStatus
    created_at: datetime
    updated_at: datetime
    reviewer_id: str | None = None
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    blockchain_tx_id: str | None = None
    blockchain_status: BlockchainSubmissionStatus | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class TransferAuditEvent:
    event_id: str
    request_id: str
    event_type: str
    actor_id: str
    actor_role: Role
    from_status: TransferStatus | None
    to_status: TransferStatus
    reason: str | None
    created_at: datetime

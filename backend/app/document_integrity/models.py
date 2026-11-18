"""Document integrity domain models and enums."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


def utc_now():
    return datetime.now(timezone.utc)


class DocumentVerificationStatus(str, Enum):
    """Result of a document integrity verification."""

    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class DocumentHash:
    """A trusted SHA-256 hash of a document, stored for integrity verification."""

    document_id: str
    parcel_id: str | None
    document_name: str
    document_hash: str  # SHA-256 hex digest
    uploaded_by: str
    uploaded_at: datetime
    verification_count: int = 0
    last_verified_at: datetime | None = None
    last_verification_status: DocumentVerificationStatus | None = None


@dataclass(frozen=True)
class DocumentVerificationResult:
    """Result of verifying a document against its trusted hash."""

    document_id: str
    document_name: str
    document_hash: str  # The stored trusted hash
    calculated_hash: str  # The hash recalculated from the provided document
    status: DocumentVerificationStatus
    verified_at: datetime
    match: bool
    parcel_id: str | None = None
    failure_reason: str | None = None

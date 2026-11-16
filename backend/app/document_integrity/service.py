"""Document integrity service: SHA-256 hashing, storage, and verification."""

import hashlib
import uuid
from typing import Optional

from app.auth.errors import (
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
    RegistryUnavailableError,
)
from app.document_integrity.models import (
    DocumentHash,
    DocumentVerificationResult,
    DocumentVerificationStatus,
    utc_now,
)
from app.document_integrity.validation import validate_document_name


class DocumentIntegrityService:
    """Service for SHA-256 document integrity verification.

    Provides three operations:

    1. ``store_document_hash`` - Calculate the SHA-256 hash of a document and
       store it as the trusted original for future verification.
    2. ``verify_document`` - Recalculate the SHA-256 hash of a provided document
       and compare it against the trusted stored hash.
    3. ``get_verification_history`` - Retrieve verification history for a parcel.
    """

    def __init__(self, repository=None):
        self._repository = repository

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    @staticmethod
    def calculate_sha256(content: bytes) -> str:
        """Calculate the SHA-256 hash of document content.

        Returns the lowercase hexadecimal digest.
        """
        if not isinstance(content, (bytes, bytearray)):
            raise InvalidInputError(
                "Document content must be bytes.", field="document"
            )
        return hashlib.sha256(content).hexdigest()

    def store_document_hash(
        self,
        document_name: str,
        document_content: bytes,
        uploaded_by: str,
        parcel_id: Optional[str] = None,
    ) -> DocumentHash:
        """Calculate and store the trusted SHA-256 hash of a document.

        Args:
            document_name: Human-readable name of the document.
            document_content: Raw bytes of the document to hash.
            uploaded_by: User ID of the person uploading the document.
            parcel_id: Optional parcel ID the document relates to.

        Returns:
            The stored DocumentHash domain object.

        Raises:
            InvalidInputError: If the document name is invalid or content is empty.
            ResourceConflictError: If a document with the same name already exists
                for the same parcel.
        """
        validate_document_name(document_name)

        if not document_content:
            raise InvalidInputError(
                "Document content cannot be empty.", field="document"
            )

        document_hash = self.calculate_sha256(document_content)

        repository = self._require_repository()

        # Check for duplicate document name per parcel
        existing = repository.find_by_name_and_parcel(document_name, parcel_id)
        if existing is not None:
            raise ResourceConflictError(
                f"A document named '{document_name}' already exists "
                f"for parcel {parcel_id or '(no parcel)'}.",
                field="document_name",
            )

        now = utc_now()
        document = DocumentHash(
            document_id=f"doc-{uuid.uuid4().hex}",
            parcel_id=parcel_id,
            document_name=document_name.strip(),
            document_hash=document_hash,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            verification_count=0,
            last_verified_at=None,
            last_verification_status=None,
        )

        return repository.create_document_hash(document)

    def verify_document(
        self,
        document_id: str,
        document_content: bytes,
    ) -> DocumentVerificationResult:
        """Verify a document against its trusted stored hash.

        Recalculates the SHA-256 hash of the provided document content and
        compares it against the trusted hash stored at upload time.

        Args:
            document_id: The ID of the stored document hash to verify against.
            document_content: Raw bytes of the document to verify.

        Returns:
            A DocumentVerificationResult with match status and details.

        Raises:
            ResourceNotFoundError: If no stored hash exists for the document ID.
            InvalidInputError: If the document content is empty.
        """
        if not document_content:
            raise InvalidInputError(
                "Document content cannot be empty.", field="document"
            )

        repository = self._require_repository()
        stored = repository.find_by_id(document_id)
        if stored is None:
            raise ResourceNotFoundError(
                "No trusted document hash found for this document ID."
            )

        calculated_hash = self.calculate_sha256(document_content)
        match = calculated_hash == stored.document_hash

        if match:
            status = DocumentVerificationStatus.MATCHED
            failure_reason = None
        else:
            status = DocumentVerificationStatus.MISMATCHED
            failure_reason = (
                "Calculated hash does not match the trusted original hash. "
                "The document may have been modified."
            )

        now = utc_now()
        repository.increment_verification(document_id, now, status)

        return DocumentVerificationResult(
            document_id=stored.document_id,
            document_name=stored.document_name,
            document_hash=stored.document_hash,
            calculated_hash=calculated_hash,
            status=status,
            verified_at=now,
            match=match,
            parcel_id=stored.parcel_id,
            failure_reason=failure_reason,
        )

    def get_verification_history(self, parcel_id: Optional[str] = None):
        """Retrieve document verification history.

        Args:
            parcel_id: Optional parcel ID to filter results.

        Returns:
            List of DocumentHash domain objects.
        """
        repository = self._require_repository()
        return repository.list_document_hashes(parcel_id=parcel_id)

    def get_document_hash(self, document_id: str) -> Optional[DocumentHash]:
        """Retrieve a single stored document hash by ID."""
        repository = self._require_repository()
        return repository.find_by_id(document_id)

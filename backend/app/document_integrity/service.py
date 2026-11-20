"""Document integrity service: SHA-256 hashing, storage, and verification."""

import hashlib
import re
import uuid
from typing import Optional

from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
    RegistryUnavailableError,
)
from app.document_integrity.models import (
    DocumentHash,
    DocumentVerificationResult,
    DocumentVerificationStatus,
    SupportingDocument,
    utc_now,
)
from app.document_integrity.validation import validate_document_name
from app.models import OwnershipStatus, Role


# A conservative RFC-2045 token grammar for client-declared content types.
_CONTENT_TYPE_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9!#$%&'*+\-.^_`|~]*/[a-zA-Z0-9][a-zA-Z0-9!#$%&'*+\-.^_`|~]*$"
)


class DocumentIntegrityService:
    """Service for SHA-256 document integrity verification.

    Provides three operations:

    1. ``store_document_hash`` - Calculate the SHA-256 hash of a document and
       store it as the trusted original for future verification.
    2. ``verify_document`` - Recalculate the SHA-256 hash of a provided document
       and compare it against the trusted stored hash.
    3. ``get_verification_history`` - Retrieve verification history for a parcel.
    """

    def __init__(
        self,
        repository=None,
        ownership_repository=None,
        supporting_document_repository=None,
        transfer_repository=None,
    ):
        self._repository = repository
        self._ownership_repository = ownership_repository
        self._supporting_document_repository = supporting_document_repository
        self._transfer_repository = transfer_repository

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    @staticmethod
    def _normalize_role(actor_role):
        try:
            return Role(actor_role)
        except (TypeError, ValueError):
            raise AuthorizationError() from None

    def _citizen_owns_active_parcel(self, actor_id, parcel_id):
        """Check the existing citizen/ownership relationship for a parcel.

        Ownership records are the project's authoritative owner relationship;
        no separate document-assignment concept is introduced here.
        """
        if self._ownership_repository is None:
            raise RegistryUnavailableError()
        list_for_parcel = getattr(self._ownership_repository, "list_for_parcel", None)
        if not callable(list_for_parcel):
            raise RegistryUnavailableError()
        records = list_for_parcel(parcel_id)
        return any(
            record.owner_id == actor_id
            and record.status == OwnershipStatus.ACTIVE
            for record in records
        )

    def _citizen_can_access_document(self, actor_id, document):
        """Apply the existing citizen document rule to a stored record.

        A citizen may access a document they uploaded or one tied to a parcel
        they actively own. Privileged roles never use this predicate.
        """
        if document.uploaded_by == actor_id:
            return True
        return bool(document.parcel_id) and self._citizen_owns_active_parcel(
            actor_id, document.parcel_id
        )

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

    def upload_supporting_document(
        self,
        document_name: str,
        document_content: bytes,
        *,
        actor_role: Role,
        uploaded_by: str,
        parcel_id: str | None = None,
        transfer_request_id: str | None = None,
        content_type: str | None = None,
    ) -> SupportingDocument:
        """Persist a supporting document and return its metadata.

        Role rules: only Registrars, Verification Officers and Citizens may
        upload; Administrators may not.

        Optional associations:
        - ``parcel_id``: an optional parcel to associate the document with.
        - ``transfer_request_id``: an optional transfer request to associate
          the document with. When supplied, the request must exist and, when
          ``parcel_id`` is also supplied, it must match the request's parcel;
          when ``parcel_id`` is omitted it is derived from the request.

        Citizens may only attach uploads to transfer requests where they are
        the seller or canonical buyer. When no transfer request is attached
        but an explicit ``parcel_id`` is supplied, Citizens must actively own
        that parcel.
        """
        role = self._normalize_role(actor_role)
        if role not in (
            Role.REGISTRAR,
            Role.VERIFICATION_OFFICER,
            Role.CITIZEN,
        ):
            raise AuthorizationError(
                "This role may not upload supporting documents."
            )
        validate_document_name(document_name)
        if not document_content:
            raise InvalidInputError(
                "Document content cannot be empty.", field="document"
            )
        validated_content_type = self._validate_content_type(content_type)

        transfer_request, final_parcel_id = self._resolve_transfer_associations(
            parcel_id, transfer_request_id
        )

        if role is Role.CITIZEN:
            if transfer_request_id is not None:
                is_seller = transfer_request.seller_id == uploaded_by
                is_buyer = (
                    transfer_request.buyer_id is not None
                    and transfer_request.buyer_id == uploaded_by
                )
                if not (is_seller or is_buyer):
                    raise AuthorizationError(
                        "You may only attach documents to transfer requests "
                        "where you are the seller or canonical buyer."
                    )
            elif parcel_id is not None:
                if not self._citizen_owns_active_parcel(uploaded_by, final_parcel_id):
                    raise AuthorizationError(
                        "You may only attach documents to parcels you actively own."
                    )

        document = SupportingDocument(
            supporting_document_id=f"docsup-{uuid.uuid4().hex}",
            parcel_id=final_parcel_id,
            transfer_request_id=transfer_request_id,
            document_name=document_name.strip(),
            document_hash=self.calculate_sha256(document_content),
            data=document_content,
            content_type=validated_content_type,
            uploaded_by=uploaded_by,
            uploaded_at=utc_now(),
        )
        return self._require_supporting_document_repository().create_supporting_document(document)

    def get_supporting_document(self, supporting_document_id, *, actor_id, actor_role):
        """Return a supporting document, or None if the actor may not access it."""
        document = self._require_supporting_document_repository().find_by_id(
            supporting_document_id
        )
        if document is None:
            return None
        role = self._normalize_role(actor_role)
        if role is Role.CITIZEN and not self._citizen_can_access_supporting_document(
            actor_id, document
        ):
            return None
        return document

    def list_supporting_documents(self, *, actor_id, actor_role, parcel_id=None):
        """List supporting documents visible to the actor, optionally filtered by parcel."""
        documents = self._require_supporting_document_repository().list_supporting_documents(
            parcel_id=parcel_id
        )
        role = self._normalize_role(actor_role)
        if role is Role.CITIZEN:
            return [
                document
                for document in documents
                if self._citizen_can_access_supporting_document(actor_id, document)
            ]
        return documents

    def _require_supporting_document_repository(self):
        if self._supporting_document_repository is None:
            raise RegistryUnavailableError()
        return self._supporting_document_repository

    def _require_transfer_repository(self):
        if self._transfer_repository is None:
            raise RegistryUnavailableError()
        return self._transfer_repository

    def _validate_content_type(self, content_type):
        if content_type is None:
            return None
        normalized = content_type.strip() if isinstance(content_type, str) else ""
        if (
            not normalized
            or len(normalized) > 100
            or not _CONTENT_TYPE_PATTERN.fullmatch(normalized)
        ):
            raise InvalidInputError("Content type is invalid.", field="content_type")
        return normalized

    def _resolve_transfer_associations(self, parcel_id, transfer_request_id):
        """Validate optional associations; returns (transfer_request, final_parcel_id)."""
        if transfer_request_id is None:
            return None, parcel_id
        request = self._require_transfer_repository().find_by_id(transfer_request_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if parcel_id is not None and request.parcel_id != parcel_id:
            raise InvalidInputError(
                "Transfer request does not belong to the supplied parcel.",
                field="transfer_request_id",
            )
        return request, (parcel_id if parcel_id is not None else request.parcel_id)

    def _citizen_can_access_supporting_document(self, actor_id, document):
        """Citizen read access to a supporting document.

        A citizen may access a supporting document they uploaded, a document
        tied to a parcel they actively own, or a document associated with a
        transfer request where they are the seller or canonical buyer.
        """
        if document.uploaded_by == actor_id:
            return True
        if document.parcel_id is not None and self._citizen_owns_active_parcel(
            actor_id, document.parcel_id
        ):
            return True
        if document.transfer_request_id is not None:
            request = (
                self._transfer_repository.find_by_id(document.transfer_request_id)
                if self._transfer_repository is not None
                else None
            )
            if request is not None and (
                request.seller_id == actor_id
                or (
                    request.buyer_id is not None
                    and request.buyer_id == actor_id
                )
            ):
                return True
        return False

    def store_document_hash(
        self,
        document_name: str,
        document_content: bytes,
        uploaded_by: str,
        parcel_id: Optional[str] = None,
        *,
        actor_role: Role,
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
            AuthorizationError: If the actor is not a Registrar.
            InvalidInputError: If the document name is invalid or content is empty.
            ResourceConflictError: If a document with the same name already exists
                for the same parcel.
        """
        validate_document_name(document_name)

        if not document_content:
            raise InvalidInputError(
                "Document content cannot be empty.", field="document"
            )

        # Creating a trusted baseline is a Registrar-only action. Other roles
        # may upload supporting documents or verify, but may not establish the
        # trusted hash that verification compares against.
        role = self._normalize_role(actor_role)
        if role is not Role.REGISTRAR:
            raise AuthorizationError(
                "Only a registrar may create trusted document hashes."
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
        *,
        actor_id: str,
        actor_role: Role,
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

        # Verification Officers verify documents as part of their role.
        # Citizens may verify only their own uploads or documents tied to
        # parcels they actively own; they cannot probe unrelated baselines.
        role = self._normalize_role(actor_role)
        if role is Role.CITIZEN and not self._citizen_can_access_document(
            actor_id, stored
        ):
            raise AuthorizationError("You cannot verify this document.")

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

    def get_verification_history(
        self,
        parcel_id: Optional[str] = None,
        *,
        actor_id: str,
        actor_role: Role,
    ):
        """Retrieve document verification history visible to the actor.

        Privileged roles keep the unfiltered history. Citizens see only
        documents they uploaded or documents for parcels they actively own,
        using the same rule as document storage and verification.
        """
        repository = self._require_repository()
        documents = repository.list_document_hashes(parcel_id=parcel_id)
        role = self._normalize_role(actor_role)
        if role is Role.CITIZEN:
            return [
                document
                for document in documents
                if self._citizen_can_access_document(actor_id, document)
            ]
        return documents

    def get_document_hash(
        self,
        document_id: str,
        *,
        actor_id: str,
        actor_role: Role,
    ) -> Optional[DocumentHash]:
        """Retrieve a single stored document hash by ID, if the actor may see it.

        An unauthorized citizen gets ``None`` so the route can answer with a
        plain not-found response and never expose the record's metadata.
        """
        repository = self._require_repository()
        document = repository.find_by_id(document_id)
        if document is None:
            return None
        role = self._normalize_role(actor_role)
        if role is Role.CITIZEN and not self._citizen_can_access_document(
            actor_id, document
        ):
            return None
        return document

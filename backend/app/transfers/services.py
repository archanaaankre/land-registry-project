import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
    RegistryUnavailableError,
)
from app.models import (
    OwnershipStatus,
    Role,
    TransferAuditEvent,
    TransferRequest,
    TransferStatus,
    BlockchainSubmissionStatus,
    utc_now,
)
from app.registry.authorization import OWNERSHIP_RECORD_ROLES, PARCEL_READ_ROLES
from app.registry.services import OwnershipService, ParcelService
from app.registry.validation import validate_identifier
from app.transfers.repositories import TransferRepository
from app.transfers.validation import validate_transfer_submission


_ACTIVE_TRANSFER_STATUSES = {
    TransferStatus.DRAFT,
    TransferStatus.SUBMITTED,
    TransferStatus.UNDER_REVIEW,
    TransferStatus.APPROVED,
    TransferStatus.BLOCKCHAIN_PENDING,
}

_ALLOWED_TRANSITIONS = {
    TransferStatus.DRAFT: frozenset({TransferStatus.SUBMITTED, TransferStatus.CANCELLED}),
    TransferStatus.SUBMITTED: frozenset(
        {
            TransferStatus.UNDER_REVIEW,
            TransferStatus.APPROVED,
            TransferStatus.REJECTED,
            TransferStatus.CANCELLED,
        }
    ),
    TransferStatus.UNDER_REVIEW: frozenset(
        {
            TransferStatus.APPROVED,
            TransferStatus.REJECTED,
            TransferStatus.CANCELLED,
        }
    ),
    TransferStatus.APPROVED: frozenset(
        {TransferStatus.BLOCKCHAIN_PENDING, TransferStatus.FAILED}
    ),
    TransferStatus.BLOCKCHAIN_PENDING: frozenset(
        {TransferStatus.COMPLETED, TransferStatus.FAILED}
    ),
    TransferStatus.COMPLETED: frozenset(),
    TransferStatus.REJECTED: frozenset(),
    TransferStatus.FAILED: frozenset(),
    TransferStatus.CANCELLED: frozenset(),
}


class TransferService:
    def __init__(
        self,
        repository: TransferRepository | None,
        parcel_repository=None,
        ownership_repository=None,
        user_repository=None,
    ):
        self._repository = repository
        self._parcel_service = ParcelService(parcel_repository)
        self._ownership_service = OwnershipService(
            ownership_repository, parcel_repository
        )
        self._user_repository = user_repository

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    def submit_transfer(self, seller_id: str, payload: dict, actor_role: Role = Role.CITIZEN):
        validated = validate_transfer_submission(payload)
        parcel_id = validated["parcel_id"]
        buyer_reference = validated["buyer_reference"]

        repository = self._require_repository()
        parcel = self._parcel_service.get_parcel(parcel_id)

        if not self._is_current_owner(seller_id, parcel_id):
            raise AuthorizationError("You are not the current owner of this parcel.")

        if seller_id == buyer_reference:
            raise InvalidInputError(
                "The buyer must be different from the seller.",
                field="buyer_reference",
            )

        self._validate_buyer(buyer_reference)

        existing = repository.find_active_for_parcel(parcel_id)
        if existing is not None:
            raise ResourceConflictError("An active transfer request already exists for this parcel.")

        now = utc_now()
        request = TransferRequest(
            request_id=f"transfer-{uuid.uuid4().hex}",
            parcel_id=parcel_id,
            seller_id=seller_id,
            buyer_reference=buyer_reference,
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
            blockchain_status=BlockchainSubmissionStatus.NOT_SUBMITTED,
        )
        saved = repository.create_request(request)
        repository.record_audit_event(
            TransferAuditEvent(
                event_id=f"event-{uuid.uuid4().hex}",
                request_id=saved.request_id,
                event_type="TRANSFER_SUBMITTED",
                actor_id=seller_id,
                actor_role=actor_role,
                from_status=None,
                to_status=TransferStatus.SUBMITTED,
                reason=None,
                created_at=now,
            )
        )
        return saved

    def _is_current_owner(self, seller_id: str, parcel_id: str) -> bool:
        records = self._ownership_service.list_for_parcel(parcel_id)
        return any(
            record.status == OwnershipStatus.ACTIVE and record.owner_id == seller_id
            for record in records
        )

    def _validate_buyer(self, buyer_reference: str) -> None:
        if self._user_repository is None:
            # The submission reference is retained for review, but user existence
            # cannot be verified without the auth user repository.
            return
        user = None
        if "@" in buyer_reference and hasattr(self._user_repository, "get_user_by_email"):
            user = self._user_repository.get_user_by_email(buyer_reference)
        elif hasattr(self._user_repository, "get_user_by_id"):
            user = self._user_repository.get_user_by_id(buyer_reference)
        if user is None:
            raise ResourceNotFoundError("The buyer was not found.")

    def list_for_actor(self, actor_id: str, role: Role):
        repository = self._require_repository()
        if role == Role.CITIZEN:
            records = repository.list_for_seller(actor_id)
            buyer_matches = (
                repository.list_for_buyer_reference(actor_id)
                if hasattr(repository, "list_for_buyer_reference")
                else []
            )
            unique = {record.request_id: record for record in [*records, *buyer_matches]}
            return list(unique.values())
        if role in (Role.REGISTRAR, Role.ADMIN):
            try:
                return repository.list_all()
            except AttributeError:
                return repository.list_pending_for_review()
        return []

    def get_request(self, actor_id: str, role: Role, request_id: str):
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if not self._can_read(actor_id, role, request):
            raise AuthorizationError("You cannot view this transfer request.")
        return request

    def list_audit_events(self, actor_id: str, role: Role, request_id: str):
        request = self.get_request(actor_id, role, request_id)
        del request
        repository = self._require_repository()
        return repository.list_audit_events(request_id)

    def cancel_request(self, actor_id: str, request_id: str, reason: str | None = None):
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.seller_id != actor_id:
            raise AuthorizationError("You cannot cancel this transfer request.")
        if request.status == TransferStatus.CANCELLED:
            return request
        self._transition(request.status, TransferStatus.CANCELLED)
        now = utc_now()
        audit_reason = reason or "Cancelled by requester"
        updated = self._with_status(
            request,
            TransferStatus.CANCELLED,
            updated_at=now,
            review_reason=audit_reason if request.review_reason is None else request.review_reason,
        )
        saved = repository.save_request(updated)
        repository.record_audit_event(
            TransferAuditEvent(
                event_id=f"event-{uuid.uuid4().hex}",
                request_id=saved.request_id,
                event_type="TRANSFER_CANCELLED",
                actor_id=actor_id,
                actor_role=Role.CITIZEN,
                from_status=request.status,
                to_status=TransferStatus.CANCELLED,
                reason=audit_reason,
                created_at=now,
            )
        )
        return saved

    def review_queue(self, role: Role):
        if role not in (Role.REGISTRAR, Role.ADMIN):
            raise AuthorizationError("Only a registrar may review transfers.")
        return self._require_repository().list_pending_for_review()

    def approve_request(self, registrar_id: str, request_id: str, reason: str | None = None):
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.status == TransferStatus.APPROVED:
            return request
        self._transition(request.status, TransferStatus.APPROVED)
        now = utc_now()
        updated = self._with_status(
            request,
            TransferStatus.APPROVED,
            updated_at=now,
            reviewer_id=registrar_id,
            reviewed_at=now,
            review_reason=reason,
            blockchain_status=BlockchainSubmissionStatus.UNAVAILABLE,
            failure_reason="Blockchain integration is not available; submission was not started.",
        )
        saved = repository.save_request(updated)
        repository.record_audit_event(
            TransferAuditEvent(
                event_id=f"event-{uuid.uuid4().hex}",
                request_id=saved.request_id,
                event_type="TRANSFER_APPROVED",
                actor_id=registrar_id,
                actor_role=Role.REGISTRAR,
                from_status=request.status,
                to_status=TransferStatus.APPROVED,
                reason=reason,
                created_at=now,
            )
        )
        return saved

    def reject_request(self, registrar_id: str, request_id: str, reason: str):
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.status == TransferStatus.REJECTED:
            return request
        self._transition(request.status, TransferStatus.REJECTED)
        now = utc_now()
        updated = self._with_status(
            request,
            TransferStatus.REJECTED,
            updated_at=now,
            reviewer_id=registrar_id,
            reviewed_at=now,
            review_reason=reason,
        )
        saved = repository.save_request(updated)
        repository.record_audit_event(
            TransferAuditEvent(
                event_id=f"event-{uuid.uuid4().hex}",
                request_id=saved.request_id,
                event_type="TRANSFER_REJECTED",
                actor_id=registrar_id,
                actor_role=Role.REGISTRAR,
                from_status=request.status,
                to_status=TransferStatus.REJECTED,
                reason=reason,
                created_at=now,
            )
        )
        return saved

    def _can_read(self, actor_id: str, role: Role, request: TransferRequest) -> bool:
        if role in (Role.REGISTRAR, Role.ADMIN):
            return True
        return request.seller_id == actor_id or request.buyer_reference == actor_id

    def _transition(self, current: TransferStatus, target: TransferStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
            raise ResourceConflictError(
                f"Transfer cannot move from {current.value} to {target.value}."
            )

    def _with_status(self, request: TransferRequest, status: TransferStatus, **updates) -> TransferRequest:
        values = {
            "request_id": request.request_id,
            "parcel_id": request.parcel_id,
            "seller_id": request.seller_id,
            "buyer_reference": request.buyer_reference,
            "status": status,
            "created_at": request.created_at,
            "updated_at": updates.get("updated_at", request.updated_at),
            "reviewer_id": updates.get("reviewer_id", request.reviewer_id),
            "review_reason": updates.get("review_reason", request.review_reason),
            "reviewed_at": updates.get("reviewed_at", request.reviewed_at),
            "blockchain_tx_id": updates.get("blockchain_tx_id", request.blockchain_tx_id),
            "blockchain_status": updates.get("blockchain_status", request.blockchain_status),
            "failure_reason": updates.get("failure_reason", request.failure_reason),
        }
        return TransferRequest(**values)


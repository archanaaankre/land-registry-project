import uuid
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
from app.registry.services import OwnershipService, ParcelService
from app.registry.validation import validate_identifier
from app.transfers.authorization import TRANSFER_FINALIZE_ROLES
from app.transfers.blockchain import UnavailableBlockchainGateway
from app.transfers.repositories import TransferRepository
from app.transfers.validation import validate_transfer_submission


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
        {TransferStatus.CANCELLED, TransferStatus.BLOCKCHAIN_PENDING}
    ),
    # COMPLETED is reachable only through finalize_transfer() after the
    # blockchain gateway returns a verified confirmation; the generic
    # transition helper must never allow it.
    TransferStatus.BLOCKCHAIN_PENDING: frozenset(),
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
        blockchain_gateway=None,
    ):
        self._repository = repository
        self._parcel_service = ParcelService(parcel_repository)
        self._ownership_service = OwnershipService(
            ownership_repository, parcel_repository
        )
        self._user_repository = user_repository
        self._gateway = blockchain_gateway

    def _require_repository(self):
        if self._repository is None:
            raise RegistryUnavailableError()
        return self._repository

    def _trusted_gateway(self):
        """Return the blockchain integration boundary.

        When no gateway has been injected, the honest unavailable default is
        used: it never confirms anything, so finalization is impossible.
        """
        gateway = self._gateway
        if gateway is None:
            gateway = UnavailableBlockchainGateway()
        return gateway

    def submit_transfer(self, seller_id: str, payload: dict, actor_role: Role = Role.CITIZEN):
        validated = validate_transfer_submission(payload)
        parcel_id = validated["parcel_id"]
        buyer_reference = validated["buyer_reference"]

        repository = self._require_repository()
        parcel = self._parcel_service.get_parcel(parcel_id)

        if parcel.status.value != "ACTIVE":
            raise ResourceConflictError(
                "Transfers are only allowed for active parcels."
            )

        ownerships = self._active_ownerships(parcel_id)
        seller_ownerships = [
            record for record in ownerships if record.owner_id == seller_id
        ]
        if not seller_ownerships:
            raise AuthorizationError("You are not the current owner of this parcel.")
        if len(ownerships) != 1 or seller_ownerships[0].share != Decimal("100"):
            raise ResourceConflictError(
                "Partial-share transfers are not supported; the seller must own "
                "100% of the parcel."
            )

        buyer = self._resolve_buyer(buyer_reference)
        if seller_id == buyer.id:
            raise InvalidInputError(
                "The buyer must be different from the seller.",
                field="buyer_reference",
            )

        existing = repository.find_active_for_parcel(parcel_id)
        if existing is not None:
            raise ResourceConflictError("An active transfer request already exists for this parcel.")

        now = utc_now()
        request = TransferRequest(
            request_id=f"transfer-{uuid.uuid4().hex}",
            parcel_id=parcel_id,
            seller_id=seller_id,
            buyer_reference=buyer_reference,
            buyer_id=buyer.id,
            status=TransferStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
            blockchain_status=BlockchainSubmissionStatus.NOT_SUBMITTED,
        )
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="TRANSFER_SUBMITTED",
            actor_id=seller_id,
            actor_role=actor_role,
            from_status=None,
            to_status=TransferStatus.SUBMITTED,
            reason=None,
            created_at=now,
        )
        return repository.create_request_with_audit(request, event)

    def _active_ownerships(self, parcel_id):
        return [
            record
            for record in self._ownership_service.list_for_parcel(parcel_id)
            if record.status == OwnershipStatus.ACTIVE
        ]

    def _resolve_buyer(self, buyer_reference: str):
        if self._user_repository is None:
            raise RegistryUnavailableError()
        if "@" in buyer_reference and hasattr(
            self._user_repository, "get_user_by_email"
        ):
            user = self._user_repository.get_user_by_email(buyer_reference)
        elif hasattr(self._user_repository, "get_user_by_id"):
            user = self._user_repository.get_user_by_id(buyer_reference)
        else:
            raise RegistryUnavailableError()
        if user is None:
            raise ResourceNotFoundError("The buyer was not found.")
        if user.role != Role.CITIZEN:
            raise InvalidInputError(
                "The buyer must have the CITIZEN role.",
                field="buyer_reference",
            )
        return user

    def _resolve_transfer_buyer(self, request: TransferRequest):
        """Resolve the transfer buyer, preferring the canonical buyer ID.

        When ``buyer_id`` exists it is authoritative: the stored reference is
        never used to re-identify the buyer, so an email change (or an email
        reused by another account) can never redirect the transfer. Legacy
        records without a canonical ID fall back to resolving
        ``buyer_reference``; an unresolvable legacy reference raises a clear
        error instead of silently assigning the transfer to anyone else.
        """
        if request.buyer_id:
            if self._user_repository is None or not hasattr(
                self._user_repository, "get_user_by_id"
            ):
                raise RegistryUnavailableError()
            user = self._user_repository.get_user_by_id(request.buyer_id)
            if user is None:
                raise ResourceNotFoundError("The buyer was not found.")
            if user.role != Role.CITIZEN:
                raise InvalidInputError(
                    "The buyer must have the CITIZEN role.",
                    field="buyer_reference",
                )
            return user
        return self._resolve_buyer(request.buyer_reference)

    def list_for_actor(self, actor_id: str, role: Role):
        repository = self._require_repository()
        if role == Role.CITIZEN:
            records = repository.list_for_seller(actor_id)
            buyer_references = {actor_id}
            buyer = self._user_by_id(actor_id)
            if buyer is not None:
                buyer_references.add(buyer.email.strip().lower())
            buyer_matches = []
            if hasattr(repository, "list_for_buyer_id"):
                canonical = repository.list_for_buyer_id(actor_id)
                # Real repositories return a list; unconfigured mocks are
                # ignored so optional repository support stays compatible.
                if isinstance(canonical, list):
                    buyer_matches.extend(canonical)
            if hasattr(repository, "list_for_buyer_reference"):
                for reference in buyer_references:
                    buyer_matches.extend(
                        repository.list_for_buyer_reference(reference)
                    )
            unique = {
                record.request_id: record
                for record in [*records, *buyer_matches]
            }
            return list(unique.values())
        if role in (Role.REGISTRAR, Role.ADMIN):
            try:
                return repository.list_all()
            except AttributeError:
                return repository.list_pending_for_review()
        return []

    def _user_by_id(self, user_id):
        if (
            self._user_repository is None
            or not hasattr(self._user_repository, "get_user_by_id")
        ):
            return None
        return self._user_repository.get_user_by_id(user_id)

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

    def list_ownership_events(self, parcel_id: str):
        """Traceable provenance for finalized transfers on a parcel.

        Entries are derived only from transfers this application actually
        completed through verified blockchain confirmation. No historical
        records are invented for legacy ownership rows.
        """
        parcel_id = validate_identifier(parcel_id, "parcel_id")
        repository = self._require_repository()
        self._parcel_service.get_parcel(parcel_id)

        events = []
        for transfer in repository.list_completed_for_parcel(parcel_id):
            finalized_at = transfer.updated_at
            for audit in repository.list_audit_events(transfer.request_id):
                if audit.event_type == "OWNERSHIP_FINALIZED":
                    finalized_at = audit.created_at
                    break
            events.append(
                {
                    "parcel_id": transfer.parcel_id,
                    "request_id": transfer.request_id,
                    "previous_owner_id": transfer.seller_id,
                    "new_owner_id": (
                        transfer.buyer_id
                        or self._buyer_user_id(transfer.buyer_reference)
                    ),
                    "finalized_at": finalized_at.isoformat(),
                    "blockchain_tx_id": transfer.blockchain_tx_id,
                }
            )
        return events

    def _buyer_user_id(self, buyer_reference: str):
        """Resolve a buyer reference to a stable user ID when possible."""
        reference = (buyer_reference or "").strip()
        if "@" in reference:
            if self._user_repository is None or not hasattr(
                self._user_repository, "get_user_by_email"
            ):
                return None
            user = self._user_repository.get_user_by_email(reference)
            return user.id if user is not None else None
        if self._user_repository is not None and hasattr(
            self._user_repository, "get_user_by_id"
        ):
            user = self._user_repository.get_user_by_id(reference)
            if user is not None:
                return user.id
        return reference

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
        if request.status == TransferStatus.APPROVED and (
            request.blockchain_status
            not in (
                None,
                BlockchainSubmissionStatus.UNAVAILABLE,
                BlockchainSubmissionStatus.NOT_SUBMITTED,
            )
        ):
            raise ResourceConflictError(
                "An approved transfer cannot be cancelled while blockchain "
                "processing may be in progress."
            )
        self._transition(request.status, TransferStatus.CANCELLED)
        now = utc_now()
        audit_reason = reason or "Cancelled by requester"
        updated = self._with_status(
            request,
            TransferStatus.CANCELLED,
            updated_at=now,
            review_reason=audit_reason if request.review_reason is None else request.review_reason,
        )
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="TRANSFER_CANCELLED",
            actor_id=actor_id,
            actor_role=Role.CITIZEN,
            from_status=request.status,
            to_status=TransferStatus.CANCELLED,
            reason=audit_reason,
            created_at=now,
        )
        return repository.save_request_with_audit(updated, request.status, event)

    def review_queue(self, role: Role):
        if role not in (Role.REGISTRAR, Role.ADMIN):
            raise AuthorizationError("Only a registrar may review transfers.")
        return self._require_repository().list_pending_for_review()

    def start_review(
        self, actor_id: str, role: Role, request_id: str, reason: str | None = None
    ):
        """Move a SUBMITTED transfer into UNDER_REVIEW.

        Only the reviewer role may start a review. Starting a transfer that is
        already under review is idempotent and returns it unchanged without
        recording a duplicate audit event; the persistence layer's
        compare-and-set rejects the losing writer of a concurrent start. Any
        state other than SUBMITTED is refused by the state machine.
        """
        if role not in (Role.REGISTRAR, Role.ADMIN):
            raise AuthorizationError("Only a registrar may review transfers.")
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.status == TransferStatus.UNDER_REVIEW:
            return request
        self._transition(request.status, TransferStatus.UNDER_REVIEW)
        now = utc_now()
        updated = self._with_status(
            request,
            TransferStatus.UNDER_REVIEW,
            updated_at=now,
            reviewer_id=actor_id,
            reviewed_at=now,
            review_reason=reason,
        )
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="TRANSFER_REVIEW_STARTED",
            actor_id=actor_id,
            actor_role=role,
            from_status=request.status,
            to_status=TransferStatus.UNDER_REVIEW,
            reason=reason,
            created_at=now,
        )
        return repository.save_request_with_audit(
            updated, request.status, event
        )

    def approve_request(self, registrar_id: str, request_id: str, reason: str | None = None):
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.status == TransferStatus.APPROVED:
            return request
        self._transition(request.status, TransferStatus.APPROVED)
        self._validate_current_transfer_state(request)
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
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="TRANSFER_APPROVED",
            actor_id=registrar_id,
            actor_role=Role.REGISTRAR,
            from_status=request.status,
            to_status=TransferStatus.APPROVED,
            reason=reason,
            created_at=now,
        )
        return repository.save_request_with_audit(updated, request.status, event)

    def _validate_current_transfer_state(self, request):
        parcel = self._parcel_service.get_parcel(request.parcel_id)
        if parcel.status.value != "ACTIVE":
            raise ResourceConflictError(
                "Transfers are only allowed for active parcels."
            )
        active_ownerships = self._active_ownerships(request.parcel_id)
        seller_ownerships = [
            ownership
            for ownership in active_ownerships
            if ownership.owner_id == request.seller_id
        ]
        if not seller_ownerships:
            raise ResourceConflictError(
                "The seller is no longer a current owner of this parcel."
            )
        if (
            len(active_ownerships) != 1
            or seller_ownerships[0].share != Decimal("100")
        ):
            raise ResourceConflictError(
                "The seller must own 100% of the parcel to transfer it."
            )
        self._resolve_transfer_buyer(request)

    def submit_to_blockchain(self, actor_id: str, role: Role, request_id: str):
        """Submit an approved transfer through the blockchain gateway.

        The gateway is the agreed integration boundary (Person 1). Without an
        injected gateway this reports registry unavailable and changes
        nothing; approval alone is never treated as submission.
        """
        if role not in (Role.REGISTRAR, Role.ADMIN):
            raise AuthorizationError(
                "Only a registrar may submit transfers to the blockchain."
            )
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")
        if request.status == TransferStatus.BLOCKCHAIN_PENDING:
            return request
        self._transition(request.status, TransferStatus.BLOCKCHAIN_PENDING)
        self._validate_current_transfer_state(request)

        submission = self._trusted_gateway().submit(request)
        if submission.status == BlockchainSubmissionStatus.UNAVAILABLE:
            raise RegistryUnavailableError(
                submission.failure_reason
                or "Blockchain integration is not available; submission was not started."
            )
        if submission.status not in (
            BlockchainSubmissionStatus.PENDING,
            BlockchainSubmissionStatus.SUBMITTED,
        ):
            raise ResourceConflictError(
                submission.failure_reason
                or "The blockchain submission failed; the transfer was not submitted."
            )
        if not submission.tx_id:
            raise ResourceConflictError(
                "The blockchain integration did not return a transaction reference."
            )

        now = utc_now()
        updated = self._with_status(
            request,
            TransferStatus.BLOCKCHAIN_PENDING,
            updated_at=now,
            blockchain_tx_id=submission.tx_id,
            blockchain_status=submission.status,
            failure_reason=None,
        )
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="BLOCKCHAIN_SUBMITTED",
            actor_id=actor_id,
            actor_role=role,
            from_status=request.status,
            to_status=TransferStatus.BLOCKCHAIN_PENDING,
            reason=f"Blockchain transaction {submission.tx_id} submitted.",
            created_at=now,
        )
        return repository.save_request_with_audit(updated, request.status, event)

    def finalize_transfer(self, actor_id: str, role: Role, request_id: str):
        """Finalize ownership after a verified blockchain confirmation.

        The confirmation is always fetched from the trusted gateway; callers
        can never supply it, so no client can mark a transfer as
        blockchain-confirmed. Ownership deactivation, buyer ownership
        creation, the COMPLETED status, and the audit event are written in
        one database transaction by the repository, which rolls everything
        back on failure. Repeated confirmation notifications are idempotent.
        """
        if role not in TRANSFER_FINALIZE_ROLES:
            raise AuthorizationError("Only a registrar may finalize transfers.")
        repository = self._require_repository()
        validated_id = validate_identifier(request_id, "request_id")
        request = repository.find_by_id(validated_id)
        if request is None:
            raise ResourceNotFoundError("Transfer request was not found.")

        if request.status == TransferStatus.COMPLETED:
            # Repeated confirmation notification: already finalized.
            return request

        if request.status != TransferStatus.BLOCKCHAIN_PENDING:
            raise ResourceConflictError(
                "Ownership can only be finalized for a transfer that is "
                "pending blockchain confirmation."
            )
        if request.blockchain_status not in (
            BlockchainSubmissionStatus.PENDING,
            BlockchainSubmissionStatus.SUBMITTED,
        ):
            raise ResourceConflictError(
                "The transfer has no submitted blockchain transaction to confirm."
            )

        confirmation = self._trusted_gateway().verify_confirmation(
            request.request_id
        )
        if confirmation is None:
            raise ResourceConflictError(
                "No verified blockchain confirmation exists for this transfer."
            )
        if (
            confirmation.request_id != request.request_id
            or confirmation.parcel_id != request.parcel_id
            or confirmation.tx_id != request.blockchain_tx_id
        ):
            raise ResourceConflictError(
                "The blockchain confirmation does not match this transfer."
            )
        if confirmation.status == BlockchainSubmissionStatus.FAILED:
            raise ResourceConflictError(
                confirmation.failure_reason
                or "The blockchain transaction failed."
            )
        if (
            confirmation.status != BlockchainSubmissionStatus.CONFIRMED
            or not confirmation.verified
        ):
            raise ResourceConflictError(
                "The blockchain transaction is not verified as confirmed."
            )

        # Party and parcel eligibility; re-checked inside the transaction.
        parcel = self._parcel_service.get_parcel(request.parcel_id)
        if parcel.status.value != "ACTIVE":
            raise ResourceConflictError(
                "Transfers are only allowed for active parcels."
            )
        buyer = self._resolve_transfer_buyer(request)
        if buyer.id == request.seller_id:
            raise InvalidInputError(
                "The buyer must be different from the seller.",
                field="buyer_reference",
            )
        active_ownerships = self._active_ownerships(request.parcel_id)
        seller_ownerships = [
            ownership
            for ownership in active_ownerships
            if ownership.owner_id == request.seller_id
        ]
        if not seller_ownerships:
            raise ResourceConflictError(
                "The seller is no longer a current owner of this parcel."
            )
        if (
            len(active_ownerships) != 1
            or seller_ownerships[0].share != Decimal("100")
        ):
            raise ResourceConflictError(
                "Partial-share transfers are not supported; the seller must "
                "own 100% of the parcel."
            )

        now = utc_now()
        finalized = self._with_status(
            request,
            TransferStatus.COMPLETED,
            updated_at=now,
            blockchain_tx_id=confirmation.tx_id,
            blockchain_status=BlockchainSubmissionStatus.CONFIRMED,
            failure_reason=None,
        )
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="OWNERSHIP_FINALIZED",
            actor_id=actor_id,
            actor_role=role,
            from_status=TransferStatus.BLOCKCHAIN_PENDING,
            to_status=TransferStatus.COMPLETED,
            reason=(
                "Ownership finalized after verified blockchain transaction "
                f"{confirmation.tx_id}."
            ),
            created_at=now,
        )
        return repository.finalize_ownership(
            finalized,
            expected_status=TransferStatus.BLOCKCHAIN_PENDING,
            buyer_id=buyer.id,
            buyer_ownership_id=f"ownership-{uuid.uuid4().hex}",
            event=event,
        )

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
        event = TransferAuditEvent(
            event_id=f"event-{uuid.uuid4().hex}",
            request_id=request.request_id,
            event_type="TRANSFER_REJECTED",
            actor_id=registrar_id,
            actor_role=Role.REGISTRAR,
            from_status=request.status,
            to_status=TransferStatus.REJECTED,
            reason=reason,
            created_at=now,
        )
        return repository.save_request_with_audit(updated, request.status, event)

    def _can_read(self, actor_id: str, role: Role, request: TransferRequest) -> bool:
        if role in (Role.REGISTRAR, Role.ADMIN):
            return True
        if request.seller_id == actor_id:
            return True
        # Canonical buyer identity keeps buyer access stable across email
        # changes; reference-based checks remain for legacy records only.
        if request.buyer_id is not None and request.buyer_id == actor_id:
            return True
        if request.buyer_reference == actor_id:
            return True
        buyer = self._user_by_id(actor_id)
        return (
            buyer is not None
            and "@" in request.buyer_reference
            and buyer.email.strip().lower() == request.buyer_reference.strip().lower()
        )

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
            "buyer_id": request.buyer_id,
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

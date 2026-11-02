"""Blockchain integration contract for transfer finalization.

Person 1 owns the blockchain integration. This module defines only the
interface the registry consumes; it never submits a transaction and never
verifies anything on-chain. A real integration must be injected through
``app.config["BLOCKCHAIN_GATEWAY"]`` and must implement ``BlockchainGateway``.

The default ``UnavailableBlockchainGateway`` is an honest placeholder: it
reports that no integration is available and always returns ``None`` for
confirmations, so ownership can never change until a real gateway that
independently verifies transactions is provided.

Confirmation contract:

* ``submit`` is called for an approved transfer and must return a
  ``SUBMITTED`` or ``PENDING`` result carrying the ledger transaction ID.
* ``verify_confirmation`` is the trusted verification boundary. It may return
  ``None`` (no confirmation exists yet) or a ``BlockchainConfirmation``.
  ``verified`` must only be ``True`` after the transaction was read back from
  the ledger (receipt, chaincode event, or state proof) and matched to this
  transfer. A status field alone is never sufficient proof of confirmation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models import BlockchainSubmissionStatus, TransferRequest


@dataclass(frozen=True)
class BlockchainSubmission:
    """Result of asking the integration to submit an approved transfer."""

    request_id: str
    status: BlockchainSubmissionStatus
    tx_id: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class BlockchainConfirmation:
    """Verification result produced by the trusted integration boundary.

    ``verified`` is the flag the finalization workflow trusts. It must only be
    set to ``True`` when the integration has independently confirmed the
    transaction on the ledger and matched it to ``request_id``/``parcel_id``.
    """

    request_id: str
    parcel_id: str
    tx_id: str
    status: BlockchainSubmissionStatus
    verified: bool
    confirmed_at: datetime
    failure_reason: str | None = None


class BlockchainGateway(Protocol):
    """Integration boundary agreed with Person 1 (blockchain owner)."""

    def submit(self, request: TransferRequest) -> BlockchainSubmission: ...

    def verify_confirmation(
        self, request_id: str
    ) -> BlockchainConfirmation | None: ...


@dataclass(frozen=True)
class UnavailableBlockchainGateway:
    """Honest default used until Person 1 provides a real gateway.

    It never starts a blockchain submission and never returns a confirmation,
    so finalization stays impossible and no fake confirmation can exist.
    """

    reason: str = "Blockchain integration is not available."

    def submit(self, request: TransferRequest) -> BlockchainSubmission:
        return BlockchainSubmission(
            request_id=request.request_id,
            status=BlockchainSubmissionStatus.UNAVAILABLE,
            failure_reason=self.reason,
        )

    def verify_confirmation(self, request_id: str) -> None:
        return None

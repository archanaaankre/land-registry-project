"""Hyperledger Fabric blockchain gateway implementation.

This module provides a real ``BlockchainGateway`` implementation backed by
Hyperledger Fabric. It conforms exactly to the protocol defined in
``app.transfers.blockchain`` and is injected through
``app.config["BLOCKCHAIN_GATEWAY"]``.

The Fabric Python SDK (``fabric-gateway``) is not published on PyPI and is
therefore not a hard dependency. When the SDK or connection configuration is
unavailable, this gateway behaves like ``UnavailableBlockchainGateway``:
it reports ``UNAVAILABLE`` for submissions and returns ``None`` for
confirmations, so no fake transaction IDs or confirmations can ever be
produced.

Chaincode compatibility (to be agreed with the chaincode author):

Transaction names and argument formats are the expected interface to the
planned Go chaincode. They are documented here for coordination only; they
are not exercised until an actual Fabric network and chaincode are deployed.

* ``RegisterParcel``:
    args: [parcel_id, cadastral_number, location, area, area_unit, owner_id]
    returns: { transaction_id }

* ``SubmitTransfer``:
    args: [request_id, parcel_id, seller_id, buyer_id]
    returns: { transaction_id }

* ``ApproveTransfer``:
    args: [request_id]
    returns: { transaction_id }

* ``ConfirmTransfer``:
    args: [request_id, tx_id]
    returns: { transaction_id }

* ``GetParcel``:
    args: [parcel_id]
    returns: { parcel_id, cadastral_number, location, area, area_unit,
               status, owner_id, created_at, updated_at, blockchain_tx_id }

* ``GetTransfer``:
    args: [request_id]
    returns: { request_id, parcel_id, seller_id, buyer_id, status,
               blockchain_tx_id, submitted_at, confirmed_at }

* ``GetParcelHistory``:
    args: [parcel_id]
    returns: [ { request_id, parcel_id, seller_id, buyer_id, status,
                 submitted_at, confirmed_at, blockchain_tx_id } ]
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models import BlockchainSubmissionStatus, TransferRequest
from app.transfers.blockchain import (
    BlockchainConfirmation,
    BlockchainSubmission,
    BlockchainGateway,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_request_id() -> str:
    return f"fabric-{uuid.uuid4().hex}"


class FabricBlockchainGateway(BlockchainGateway):
    """Hyperledger Fabric-backed blockchain gateway.

    Connects to a Fabric network using the Fabric Gateway Python SDK
    (``fabric_gateway``). When the SDK or connection configuration is not
    available, all submission attempts report ``UNAVAILABLE`` and all
    confirmation queries return ``None``, so ownership can never change
    until a real gateway that independently verifies transactions is
    provided.

    Configuration is read from environment variables via Flask
    ``app.config``:

    * ``FABRIC_CONNECTION_PROFILE`` — path to the Fabric connection profile
      (CCP) JSON file.
    * ``FABRIC_CHANNEL`` — channel name.
    * ``FABRIC_CHAINCODE_NAME`` — chaincode name (default: ``land-registry``).
    * ``FABRIC_USER`` — enrolled Fabric user identity (MSP ID + user name).
    * ``FABRIC_WALLET_PATH`` — path to the identity wallet directory.

    None of these values are secrets themselves; they point to wallet
    directories and connection profiles that the deployer manages
    separately.
    """

    def __init__(
        self,
        *,
        connection_profile: Optional[str] = None,
        channel: Optional[str] = None,
        chaincode_name: Optional[str] = None,
        user: Optional[str] = None,
        wallet_path: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        self._connection_profile = connection_profile
        self._channel = channel
        self._chaincode_name = chaincode_name or "land-registry"
        self._user = user
        self._wallet_path = wallet_path
        self._reason = reason or "Blockchain integration is not available."
        self._gateway = None
        self._network = None
        self._contract = None
        self._initialized = False
        self._init_error: Optional[str] = None

        # Lazily initialize so that missing config does not crash app startup.
        self._try_initialize()

    def _try_initialize(self) -> None:
        """Attempt to initialize the Fabric Gateway connection.

        Any failure is recorded but not raised, so that the gateway can
        degrade gracefully to an unavailable state.
        """
        if self._initialized:
            return
        self._initialized = True

        missing = []
        if not self._connection_profile:
            missing.append("FABRIC_CONNECTION_PROFILE")
        if not self._channel:
            missing.append("FABRIC_CHANNEL")
        if not self._user:
            missing.append("FABRIC_USER")
        if not self._wallet_path:
            missing.append("FABRIC_WALLET_PATH")

        if missing:
            self._init_error = (
                "Fabric configuration missing: " + ", ".join(missing)
            )
            return

        try:
            # The Fabric Gateway Python SDK is not published on PyPI and is
            # therefore not a guaranteed dependency. Importing it here keeps
            # the hard dependency optional; when it is unavailable the
            # gateway stays in its unavailable state.
            from fabric_gateway import Gateway  # type: ignore

            self._gateway = Gateway(
                connection_profile=self._connection_profile,
                user=self._user,
                wallet_path=self._wallet_path,
            )
            self._network = self._gateway.get_network(self._channel)
            self._contract = self._network.get_contract(self._chaincode_name)
        except Exception as error:  # noqa: BLE001
            # Any SDK/connection failure is recorded; the gateway stays
            # unavailable rather than fabricating a connection.
            self._init_error = f"Fabric initialization failed: {error}"

    @property
    def is_available(self) -> bool:
        """Return True only when the Fabric gateway is initialized and reachable."""
        return self._contract is not None and self._init_error is None

    def _ensure_connected(self) -> None:
        """Raise if the Fabric contract is not available."""
        if self._init_error:
            raise RuntimeError(self._init_error)
        if self._contract is None:
            raise RuntimeError("Fabric contract is not initialized.")

    # ------------------------------------------------------------------
    # BlockchainGateway protocol
    # ------------------------------------------------------------------

    def submit(self, request: TransferRequest) -> BlockchainSubmission:
        """Submit an approved transfer to the Fabric chaincode.

        Calls the ``SubmitTransfer`` chaincode function. On success returns
        a ``SUBMITTED`` result carrying the ledger transaction ID. On any
        failure returns ``UNAVAILABLE`` or ``FAILED`` with a reason; never
        fabricates a transaction ID.
        """
        self._try_initialize()
        if not self.is_available:
            return BlockchainSubmission(
                request_id=request.request_id,
                status=BlockchainSubmissionStatus.UNAVAILABLE,
                failure_reason=self._init_error
                or "Blockchain integration is not available.",
            )

        try:
            # The Fabric SDK surface is not fixed across versions; the
            # exact submit call pattern depends on the installed
            # fabric-gateway version. When the SDK is available the
            # deployer must wire the actual chaincode invocation here
            # against the real contract object.
            tx_id = self._submit_transfer(request)
        except Exception as error:  # noqa: BLE001
            return BlockchainSubmission(
                request_id=request.request_id,
                status=BlockchainSubmissionStatus.FAILED,
                failure_reason=str(error) or "Blockchain submission failed.",
            )

        if not tx_id:
            return BlockchainSubmission(
                request_id=request.request_id,
                status=BlockchainSubmissionStatus.FAILED,
                failure_reason="The blockchain integration did not return a transaction reference.",
            )

        return BlockchainSubmission(
            request_id=request.request_id,
            status=BlockchainSubmissionStatus.SUBMITTED,
            tx_id=tx_id,
        )

    def verify_confirmation(
        self, request_id: str
    ) -> Optional[BlockchainConfirmation]:
        """Verify a blockchain confirmation from the Fabric ledger.

        Queries the ``GetTransfer`` chaincode function and confirms the
        transaction only when the ledger reports a confirmed state that
        matches ``request_id``. Returns ``None`` when no confirmation
        exists yet, never fabricates a confirmation.
        """
        self._try_initialize()
        if not self.is_available:
            return None

        try:
            transfer = self._query_transfer(request_id)
        except Exception as error:  # noqa: BLE001
            return BlockchainConfirmation(
                request_id=request_id,
                parcel_id="",
                tx_id="",
                status=BlockchainSubmissionStatus.FAILED,
                verified=False,
                confirmed_at=utc_now(),
                failure_reason=str(error) or "Blockchain confirmation query failed.",
            )

        if transfer is None:
            return None

        status = transfer.get("status")
        tx_id = transfer.get("tx_id") or transfer.get("blockchain_tx_id")
        parcel_id = transfer.get("parcel_id", "")
        confirmed_at = transfer.get("confirmed_at")

        if status == "COMPLETED" and tx_id:
            return BlockchainConfirmation(
                request_id=request_id,
                parcel_id=parcel_id,
                tx_id=tx_id,
                status=BlockchainSubmissionStatus.CONFIRMED,
                verified=True,
                confirmed_at=utc_now(),
            )

        if status == "FAILED":
            return BlockchainConfirmation(
                request_id=request_id,
                parcel_id=parcel_id,
                tx_id=tx_id or "",
                status=BlockchainSubmissionStatus.FAILED,
                verified=False,
                confirmed_at=utc_now(),
                failure_reason="The blockchain transaction failed.",
            )

        # SUBMITTED, PENDING, or any other state: not yet confirmed.
        return BlockchainConfirmation(
            request_id=request_id,
            parcel_id=parcel_id,
            tx_id=tx_id or "",
            status=BlockchainSubmissionStatus.PENDING,
            verified=False,
            confirmed_at=utc_now(),
        )

    # ------------------------------------------------------------------
    # Internal helpers (placeholders for real Fabric SDK calls)
    # ------------------------------------------------------------------

    def _submit_transfer(self, request: TransferRequest) -> Optional[str]:
        """Submit a transfer to the Fabric chaincode.

        This is where the real ``fabric_gateway`` contract call would go.
        Because the SDK surface is not fixed and is not installed in this
        environment, this method raises ``NotImplementedError`` until the
        deployer wires it to a real chaincode invocation.

        Returns the ledger transaction ID on success, or raises on failure.
        """
        self._ensure_connected()
        raise NotImplementedError(
            "Fabric SDK submit is not wired. "
            "Implement _submit_transfer() against self._contract for the "
            "deployed chaincode (SubmitTransfer function)."
        )

    def _query_transfer(self, request_id: str) -> Optional[dict[str, Any]]:
        """Query a transfer from the Fabric chaincode.

        This is where the real ``fabric_gateway`` contract query would go.
        Returns a dict with transfer fields on success, or ``None`` if the
        transfer does not exist on the ledger.

        Raises on query errors (network, chaincode error).
        """
        self._ensure_connected()
        raise NotImplementedError(
            "Fabric SDK query is not wired. "
            "Implement _query_transfer() against self._contract for the "
            "deployed chaincode (GetTransfer function)."
        )


class UnavailableFabricGateway(FabricBlockchainGateway):
    """Convenience subclass that is always unavailable.

    Useful for testing or when the deployer wants an explicit unavailable
    Fabric gateway without configuring connection details.
    """

    def __init__(self, reason: str = "Blockchain integration is not available."):
        super().__init__(
            connection_profile=None,
            channel=None,
            chaincode_name="land-registry",
            user=None,
            wallet_path=None,
            reason=reason,
        )

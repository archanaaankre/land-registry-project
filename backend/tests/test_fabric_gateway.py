"""Tests for the Hyperledger Fabric blockchain gateway.

These tests use mocks to simulate Fabric SDK behavior since the actual
fabric-gateway SDK is not published on PyPI and is not installed. No real
blockchain network is contacted; all tests are mocked at the gateway
boundary.
"""

import pytest

from app.models import (
    BlockchainSubmissionStatus,
    TransferRequest,
    TransferStatus,
    utc_now,
)
from app.transfers.blockchain import BlockchainConfirmation
from app.transfers.fabric_gateway import FabricBlockchainGateway


def _make_request(
    request_id="transfer-1",
    parcel_id="parcel-1",
    status=TransferStatus.SUBMITTED,
    blockchain_tx_id=None,
    blockchain_status=None,
):
    return TransferRequest(
        request_id=request_id,
        parcel_id=parcel_id,
        seller_id="seller-1",
        buyer_reference="buyer@example.com",
        status=status,
        created_at=utc_now(),
        updated_at=utc_now(),
        blockchain_tx_id=blockchain_tx_id,
        blockchain_status=blockchain_status,
        failure_reason=None,
    )


def _make_gateway_with_submit(
    submit_return=None,
    submit_exception=None,
):
    """Create a gateway whose _submit_transfer is mocked."""
    gateway = FabricBlockchainGateway(
        connection_profile="/fake/connection.json",
        channel="mychannel",
        chaincode_name="land-registry",
        user="registrar",
        wallet_path="/fake/wallet",
    )
    # Force initialized state so _submit_transfer is reachable.
    gateway._initialized = True
    gateway._init_error = None
    gateway._contract = object()  # non-None contract
    gateway._submit_transfer = lambda req: (
        submit_return() if callable(submit_return) else submit_return
    )
    if submit_exception:
        gateway._submit_transfer = lambda req: (_ for _ in ()).throw(
            submit_exception
        )
    return gateway


def _make_gateway_with_query(
    query_return=None,
    query_exception=None,
):
    """Create a gateway whose _query_transfer is mocked."""
    gateway = FabricBlockchainGateway(
        connection_profile="/fake/connection.json",
        channel="mychannel",
        chaincode_name="land-registry",
        user="registrar",
        wallet_path="/fake/wallet",
    )
    gateway._initialized = True
    gateway._init_error = None
    gateway._contract = object()
    gateway._query_transfer = lambda rid: (
        query_return() if callable(query_return) else query_return
    )
    if query_exception:
        gateway._query_transfer = lambda rid: (_ for _ in ()).throw(
            query_exception
        )
    return gateway


# ---------------------------------------------------------------------------
# submit() tests
# ---------------------------------------------------------------------------


def test_submit_successful_returns_submitted_with_tx_id():
    request = _make_request(status=BlockchainSubmissionStatus.NOT_SUBMITTED)
    gateway = _make_gateway_with_submit(submit_return="fabric-tx-abc123")

    result = gateway.submit(request)

    assert result.request_id == request.request_id
    assert result.status is BlockchainSubmissionStatus.SUBMITTED
    assert result.tx_id == "fabric-tx-abc123"
    assert result.failure_reason is None


def test_submit_with_no_tx_id_returns_failed():
    request = _make_request()
    gateway = _make_gateway_with_submit(submit_return=None)

    result = gateway.submit(request)

    assert result.status is BlockchainSubmissionStatus.FAILED
    assert result.tx_id is None
    assert "did not return a transaction reference" in result.failure_reason


def test_submit_with_exception_returns_failed():
    request = _make_request()
    gateway = _make_gateway_with_submit(
        submit_exception=RuntimeError("chaincode error")
    )

    result = gateway.submit(request)

    assert result.status is BlockchainSubmissionStatus.FAILED
    assert "chaincode error" in result.failure_reason


def test_submit_when_unavailable_returns_unavailable():
    request = _make_request()
    # No configuration provided -> unavailable.
    gateway = FabricBlockchainGateway()

    result = gateway.submit(request)

    assert result.status is BlockchainSubmissionStatus.UNAVAILABLE
    assert result.tx_id is None
    assert result.failure_reason is not None


# ---------------------------------------------------------------------------
# verify_confirmation() tests
# ---------------------------------------------------------------------------


def test_verify_confirmation_successful_returns_confirmed():
    gateway = _make_gateway_with_query(
        query_return={
            "status": "COMPLETED",
            "tx_id": "fabric-tx-abc123",
            "parcel_id": "parcel-1",
            "confirmed_at": utc_now().isoformat(),
        }
    )
    request = _make_request(
        blockchain_tx_id="fabric-tx-abc123",
        blockchain_status=BlockchainSubmissionStatus.SUBMITTED,
    )

    confirmation = gateway.verify_confirmation(request.request_id)

    assert confirmation is not None
    assert confirmation.request_id == request.request_id
    assert confirmation.parcel_id == "parcel-1"
    assert confirmation.tx_id == "fabric-tx-abc123"
    assert confirmation.status is BlockchainSubmissionStatus.CONFIRMED
    assert confirmation.verified is True


def test_verify_confirmation_no_confirmation_returns_none():
    gateway = _make_gateway_with_query(query_return=None)

    confirmation = gateway.verify_confirmation("transfer-nonexistent")

    assert confirmation is None


def test_verify_confirmation_failed_transfer_returns_failed():
    gateway = _make_gateway_with_query(
        query_return={
            "status": "FAILED",
            "tx_id": "fabric-tx-abc123",
            "parcel_id": "parcel-1",
        }
    )

    confirmation = gateway.verify_confirmation("transfer-1")

    assert confirmation is not None
    assert confirmation.status is BlockchainSubmissionStatus.FAILED
    assert confirmation.verified is False
    assert "failed" in (confirmation.failure_reason or "").lower()


def test_verify_confirmation_pending_returns_pending_not_verified():
    gateway = _make_gateway_with_query(
        query_return={
            "status": "SUBMITTED",
            "tx_id": "fabric-tx-abc123",
            "parcel_id": "parcel-1",
        }
    )

    confirmation = gateway.verify_confirmation("transfer-1")

    assert confirmation is not None
    assert confirmation.status is BlockchainSubmissionStatus.PENDING
    assert confirmation.verified is False


def test_verify_confirmation_when_unavailable_returns_none():
    gateway = FabricBlockchainGateway()

    confirmation = gateway.verify_confirmation("transfer-1")

    assert confirmation is None


def test_verify_confirmation_query_exception_returns_failed_confirmation():
    gateway = _make_gateway_with_query(
        query_exception=RuntimeError("ledger query error")
    )

    confirmation = gateway.verify_confirmation("transfer-1")

    assert confirmation is not None
    assert confirmation.status is BlockchainSubmissionStatus.FAILED
    assert confirmation.verified is False
    assert "ledger query error" in confirmation.failure_reason


# ---------------------------------------------------------------------------
# Idempotency / repeated confirmation
# ---------------------------------------------------------------------------


def test_repeated_confirmation_returns_same_result():
    gateway = _make_gateway_with_query(
        query_return={
            "status": "COMPLETED",
            "tx_id": "fabric-tx-abc123",
            "parcel_id": "parcel-1",
        }
    )

    first = gateway.verify_confirmation("transfer-1")
    second = gateway.verify_confirmation("transfer-1")

    assert first is not None
    assert second is not None
    assert first.tx_id == second.tx_id
    assert first.verified == second.verified == True


# ---------------------------------------------------------------------------
# is_available property
# ---------------------------------------------------------------------------


def test_is_available_when_configured_and_initialized():
    gateway = _make_gateway_with_submit(submit_return="fabric-tx-abc123")
    assert gateway.is_available is True


def test_is_available_when_not_configured():
    gateway = FabricBlockchainGateway()
    assert gateway.is_available is False


def test_is_available_when_initialization_failed():
    gateway = FabricBlockchainGateway(
        connection_profile=None,
        channel=None,
        chaincode_name="land-registry",
        user=None,
        wallet_path=None,
    )
    assert gateway.is_available is False


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_fabric_gateway_implements_protocol():
    gateway = FabricBlockchainGateway()
    assert isinstance(gateway, FabricBlockchainGateway)
    assert hasattr(gateway, "submit")
    assert hasattr(gateway, "verify_confirmation")

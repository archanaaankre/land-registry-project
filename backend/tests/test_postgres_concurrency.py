"""PostgreSQL concurrency and data integrity tests.

These tests exercise genuine parallel transactions against an isolated,
disposable embedded PostgreSQL server (the ``pgserver`` package): real row
locks (``SELECT ... FOR UPDATE``), compare-and-set updates, partial unique
indexes, and check constraints behave exactly as they do in production.

The whole module is skipped when ``pgserver`` is unavailable. SQLite's
locking proves nothing about PostgreSQL concurrency, so the SQLite suite is
never treated as a substitute for these tests.
"""

import os
import shutil
import tempfile
import threading
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip(
    "pgserver",
    reason="pgserver provides the disposable PostgreSQL test server "
    "(pip install pgserver); without it PostgreSQL concurrency remains "
    "unverified and this module must not silently fall back to SQLite.",
)

import psycopg2

from app import create_app, db
from app.auth.errors import (
    AuthError,
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from app.auth.service import hash_password
from app.config import Config
from app.models import (
    AreaUnit,
    BlockchainSubmissionStatus,
    Ownership,
    OwnershipStatus,
    Parcel,
    ParcelStatus,
    Role,
    TransferAuditEvent,
    TransferStatus,
    utc_now,
)
from app.persistence.models import TransferAuditEventModel
from app.persistence.repositories import (
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
)
from app.registry.services import OwnershipService
from app.transfers.blockchain import BlockchainConfirmation, BlockchainSubmission
from app.transfers.services import TransferService

PARCEL_ID = "parcel-pg"
TX_ID = "0xpg-concurrency-tx"


# ---------------------------------------------------------------------------
# Disposable PostgreSQL server and per-test database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_server():
    """One isolated embedded PostgreSQL server for the whole module.

    It listens on a random localhost port with its own data directory under
    the approved temp area; nothing shared or production-like is touched, and
    ``cleanup()`` stops the server and removes its data directory afterwards.
    """
    base = os.path.join(tempfile.gettempdir(), "opencode")
    os.makedirs(base, exist_ok=True)
    datadir = os.path.join(base, "pg_concurrency_" + uuid.uuid4().hex[:8])
    server = pgserver.get_server(datadir)
    try:
        yield server
    finally:
        server.cleanup()
        shutil.rmtree(datadir, ignore_errors=True)


@pytest.fixture
def pg_app(postgres_server):
    """A fresh application bound to a unique database on that server.

    Each test gets its own ``CREATE DATABASE`` so tests cannot observe each
    other's rows. The databases are never dropped explicitly: they live only
    inside the disposable server instance that is removed at session end.
    """
    dbname = "concurrency_" + uuid.uuid4().hex[:12]
    admin = psycopg2.connect(postgres_server.get_uri())
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        admin.close()
    database_url = postgres_server.get_uri().rsplit("/", 1)[0] + "/" + dbname
    app = _prepare_app(database_url)
    yield app
    with app.app_context():
        db.engine.dispose()


def _prepare_app(database_url):
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    app = create_app()
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-jwt-secret-for-postgres-concurrency",
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with app.app_context():
        db.create_all()
    app.config.update(
        AUTH_USER_REPOSITORY=SqlAlchemyUserRepository(),
        PARCEL_REPOSITORY=SqlAlchemyParcelRepository(),
        OWNERSHIP_REPOSITORY=SqlAlchemyOwnershipRepository(),
        TRANSFER_REPOSITORY=SqlAlchemyTransferRepository(),
    )
    return app


# ---------------------------------------------------------------------------
# Services, stub gateway, seeding
# ---------------------------------------------------------------------------


class StubBlockchainGateway:
    """Test double standing in for Person 1's integration gateway."""

    def __init__(self, parcel_id, *, tx_id=TX_ID):
        self.parcel_id = parcel_id
        self.tx_id = tx_id

    def submit(self, request):
        return BlockchainSubmission(
            request_id=request.request_id,
            status=BlockchainSubmissionStatus.SUBMITTED,
            tx_id=self.tx_id,
        )

    def verify_confirmation(self, request_id):
        return BlockchainConfirmation(
            request_id=request_id,
            parcel_id=self.parcel_id,
            tx_id=self.tx_id,
            status=BlockchainSubmissionStatus.CONFIRMED,
            verified=True,
            confirmed_at=utc_now(),
        )


def _transfer_service(app, gateway=None):
    return TransferService(
        app.config["TRANSFER_REPOSITORY"],
        app.config["PARCEL_REPOSITORY"],
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["AUTH_USER_REPOSITORY"],
        blockchain_gateway=gateway or StubBlockchainGateway(PARCEL_ID),
    )


def _ownership_service(app):
    return OwnershipService(
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["PARCEL_REPOSITORY"],
    )


def _seed(app, *, parcel_status=ParcelStatus.ACTIVE, initial_share=Decimal("100")):
    users = app.config["AUTH_USER_REPOSITORY"]
    parcels = app.config["PARCEL_REPOSITORY"]
    ownerships = app.config["OWNERSHIP_REPOSITORY"]
    now = utc_now()
    with app.app_context():
        seller = users.create_user(
            name="Seller",
            email="pg-seller@example.com",
            password_hash=hash_password("seller password"),
            role=Role.CITIZEN,
        )
        buyer = users.create_user(
            name="Buyer",
            email="pg-buyer@example.com",
            password_hash=hash_password("buyer password"),
            role=Role.CITIZEN,
        )
        registrar = users.create_user(
            name="Registrar",
            email="pg-registrar@example.com",
            password_hash=hash_password("registrar password"),
            role=Role.REGISTRAR,
        )
        owner_b = users.create_user(
            name="Owner B",
            email="pg-owner-b@example.com",
            password_hash=hash_password("owner b password"),
            role=Role.CITIZEN,
        )
        owner_c = users.create_user(
            name="Owner C",
            email="pg-owner-c@example.com",
            password_hash=hash_password("owner c password"),
            role=Role.CITIZEN,
        )
        parcels.create_parcel(
            Parcel(
                parcel_id=PARCEL_ID,
                cadastral_number="CAD-PG",
                location="Ward PostgreSQL",
                area=Decimal("10"),
                area_unit=AreaUnit.HECTARES,
                status=parcel_status,
                created_at=now,
                updated_at=now,
            )
        )
        if initial_share > 0:
            ownerships.create_ownership(
                Ownership(
                    ownership_id="ownership-pg-seller",
                    parcel_id=PARCEL_ID,
                    owner_id=seller.id,
                    share=initial_share,
                    status=OwnershipStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
    return SimpleNamespace(
        app=app,
        seller=seller,
        buyer=buyer,
        registrar=registrar,
        owner_b=owner_b,
        owner_c=owner_c,
        parcel_id=PARCEL_ID,
    )


# ---------------------------------------------------------------------------
# Concurrency and assertion helpers
# ---------------------------------------------------------------------------


def _race(app, *operations):
    """Run operations in parallel threads and collect their outcomes.

    Returns a list of ``(kind, value)`` where kind is ``"ok"``, ``"error"``
    (an application error) or ``"unexpected"`` (anything else, which fails
    assertions deliberately).
    """
    barrier = threading.Barrier(len(operations))
    results = [None] * len(operations)

    def _run(index, operation):
        with app.app_context():
            try:
                barrier.wait(timeout=15)
            except threading.BrokenBarrierError as error:  # pragma: no cover
                results[index] = ("unexpected", error)
                return
            try:
                results[index] = ("ok", operation())
            except AuthError as error:
                results[index] = ("error", error)
            except Exception as error:  # pragma: no cover - surfaced below
                results[index] = ("unexpected", error)

    threads = [
        threading.Thread(target=_run, args=(index, operation))
        for index, operation in enumerate(operations)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), (
        "a concurrent operation deadlocked"
    )
    assert all(result is not None for result in results), (
        "a concurrent operation produced no result"
    )
    return results


def _events(app, request_id):
    with app.app_context():
        rows = app.config["TRANSFER_REPOSITORY"].list_audit_events(request_id)
    return [
        (
            row.event_type,
            row.from_status.value if row.from_status is not None else None,
            row.to_status.value,
        )
        for row in rows
    ]


def _total_event_count(app):
    with app.app_context():
        return TransferAuditEventModel.query.count()


def _assert_valid_chain(summaries):
    """Every audit event must continue where the previous one ended."""
    for previous, current in zip(summaries, summaries[1:]):
        assert previous[2] == current[1], (
            f"broken audit chain: {summaries}"
        )


def _assert_ownership_invariants(app, parcel_id):
    """Structural invariants that must hold after any race."""
    with app.app_context():
        rows = app.config["OWNERSHIP_REPOSITORY"].list_for_parcel(parcel_id)
    active = [row for row in rows if row.status is OwnershipStatus.ACTIVE]
    seen_owners = set()
    active_total = Decimal("0")
    for row in rows:
        assert row.status in (
            OwnershipStatus.ACTIVE,
            OwnershipStatus.INACTIVE,
            OwnershipStatus.DISPUTED,
        ), f"invalid ownership status: {row.status}"
        assert Decimal("0") < row.share <= Decimal("100"), (
            f"invalid share: {row.share}"
        )
    for row in active:
        assert row.owner_id not in seen_owners, (
            "duplicate active ownership for one owner"
        )
        seen_owners.add(row.owner_id)
        active_total += row.share
    assert active_total <= Decimal("100"), (
        f"active shares exceed 100%: {active_total}"
    )
    return rows


def _create_ownership_operation(app, seed, owner, share):
    def operation():
        return _ownership_service(app).create_ownership(
            {
                "ownership_id": f"ownership-pg-{uuid.uuid4().hex[:12]}",
                "parcel_id": seed.parcel_id,
                "owner_id": owner.id,
                "share": share,
                "status": "ACTIVE",
            }
        )

    return operation


def _submit_operation(app, seed):
    def operation():
        return _transfer_service(app).submit_transfer(
            seed.seller.id,
            {"parcel_id": seed.parcel_id, "buyer_reference": seed.buyer.email},
        )

    return operation


def _submitted_transfer(app, seed):
    with app.app_context():
        transfer = _submit_operation(app, seed)()
    return transfer.request_id


def _pending_transfer(app, seed):
    """Submit, approve, and blockchain-submit; return the request id."""
    with app.app_context():
        service = _transfer_service(app, StubBlockchainGateway(seed.parcel_id))
        transfer = _submit_operation(app, seed)()
        service.approve_request(seed.registrar.id, transfer.request_id)
        submitted = service.submit_to_blockchain(
            seed.registrar.id, Role.REGISTRAR, transfer.request_id
        )
    assert submitted.status is TransferStatus.BLOCKCHAIN_PENDING
    return transfer.request_id


def _assert_single_finalization(app, seed, request_id):
    """The post-conditions of exactly one applied finalization."""
    rows = _assert_ownership_invariants(app, seed.parcel_id)
    active = [row for row in rows if row.status is OwnershipStatus.ACTIVE]
    assert len(active) == 1
    assert active[0].owner_id == seed.buyer.id
    assert active[0].share == Decimal("100")

    seller_rows = [row for row in rows if row.owner_id == seed.seller.id]
    assert len(seller_rows) == 1, "the seller's record must not vanish"
    assert seller_rows[0].status is OwnershipStatus.INACTIVE
    assert seller_rows[0].share == Decimal("100")

    with app.app_context():
        stored = app.config["TRANSFER_REPOSITORY"].find_by_id(request_id)
    assert stored.status is TransferStatus.COMPLETED
    assert stored.blockchain_status is BlockchainSubmissionStatus.CONFIRMED
    assert stored.blockchain_tx_id == TX_ID

    summaries = _events(app, request_id)
    _assert_valid_chain(summaries)
    finalized = [
        summary for summary in summaries if summary[0] == "OWNERSHIP_FINALIZED"
    ]
    assert len(finalized) == 1

    provenance_service = _transfer_service(app)
    with app.app_context():
        provenance = provenance_service.list_ownership_events(seed.parcel_id)
    assert len(provenance) == 1
    assert provenance[0]["new_owner_id"] == seed.buyer.id
    assert provenance[0]["previous_owner_id"] == seed.seller.id
    assert provenance[0]["blockchain_tx_id"] == TX_ID


# ---------------------------------------------------------------------------
# Section 2: ownership concurrency
# ---------------------------------------------------------------------------


def test_concurrent_ownership_creation_cannot_exceed_100_percent(pg_app):
    app = pg_app
    seed = _seed(app, initial_share=Decimal("40"))

    results = _race(
        app,
        _create_ownership_operation(app, seed, seed.owner_b, 40),
        _create_ownership_operation(app, seed, seed.owner_c, 40),
    )

    successes = [value for kind, value in results if kind == "ok"]
    failures = [value for kind, value in results if kind == "error"]
    assert len(successes) == 1, results
    assert len(failures) == 1 and isinstance(failures[0], ResourceConflictError), (
        results
    )

    rows = _assert_ownership_invariants(app, seed.parcel_id)
    active_total = sum(
        (row.share for row in rows if row.status is OwnershipStatus.ACTIVE),
        Decimal("0"),
    )
    assert active_total == Decimal("80")


def test_concurrent_ownership_creation_cannot_duplicate_active_owner(pg_app):
    app = pg_app
    seed = _seed(app, initial_share=Decimal("0"))

    results = _race(
        app,
        _create_ownership_operation(app, seed, seed.owner_b, 50),
        _create_ownership_operation(app, seed, seed.owner_b, 50),
    )

    successes = [value for kind, value in results if kind == "ok"]
    failures = [value for kind, value in results if kind == "error"]
    assert len(successes) == 1, results
    assert len(failures) == 1 and isinstance(failures[0], ResourceConflictError), (
        results
    )

    rows = _assert_ownership_invariants(app, seed.parcel_id)
    owner_b_rows = [row for row in rows if row.owner_id == seed.owner_b.id]
    assert len(owner_b_rows) == 1
    assert owner_b_rows[0].status is OwnershipStatus.ACTIVE
    assert owner_b_rows[0].share == Decimal("50")


def test_concurrent_ownership_creation_respects_parcel_eligibility(pg_app):
    app = pg_app
    # No starting ownership: the share-amount rule must not mask the checks
    # under test (an existing 100% owner would reject any addition first).
    seed = _seed(app, initial_share=Decimal("0"))

    def create_on_missing_parcel():
        def operation():
            return _ownership_service(app).create_ownership(
                {
                    "ownership_id": f"ownership-pg-{uuid.uuid4().hex[:12]}",
                    "parcel_id": "parcel-pg-missing",
                    "owner_id": seed.owner_b.id,
                    "share": 50,
                    "status": "ACTIVE",
                }
            )

        return operation

    missing_results = _race(
        app, create_on_missing_parcel(), create_on_missing_parcel()
    )
    assert all(kind == "error" for kind, _ in missing_results), missing_results
    assert all(
        isinstance(value, ResourceNotFoundError)
        for _, value in missing_results
    ), missing_results

    non_citizen_results = _race(
        app,
        _create_ownership_operation(app, seed, seed.registrar, 50),
        _create_ownership_operation(app, seed, seed.registrar, 50),
    )
    assert all(kind == "error" for kind, _ in non_citizen_results), (
        non_citizen_results
    )
    assert all(
        isinstance(value, InvalidInputError)
        for _, value in non_citizen_results
    ), non_citizen_results

    rows = _assert_ownership_invariants(app, seed.parcel_id)
    assert rows == []


# ---------------------------------------------------------------------------
# Section 3: transfer concurrency
# ---------------------------------------------------------------------------


def test_simultaneous_submissions_create_single_active_transfer(pg_app):
    app = pg_app
    seed = _seed(app)

    results = _race(
        app, _submit_operation(app, seed), _submit_operation(app, seed)
    )

    successes = [value for kind, value in results if kind == "ok"]
    failures = [value for kind, value in results if kind == "error"]
    assert len(successes) == 1, results
    assert len(failures) == 1 and isinstance(failures[0], ResourceConflictError), (
        results
    )

    with app.app_context():
        requests = app.config["TRANSFER_REPOSITORY"].list_for_seller(
            seed.seller.id
        )
    assert len(requests) == 1, "only one active transfer may exist"
    assert requests[0].status is TransferStatus.SUBMITTED
    assert requests[0].request_id == successes[0].request_id
    # The loser's audit event was rolled back with its transaction.
    assert _total_event_count(app) == 1
    assert _events(app, requests[0].request_id)[0][0] == "TRANSFER_SUBMITTED"


def test_concurrent_submissions_respect_parcel_eligibility(pg_app):
    app = pg_app
    seed = _seed(app, parcel_status=ParcelStatus.DISPUTED)

    results = _race(
        app, _submit_operation(app, seed), _submit_operation(app, seed)
    )

    assert all(kind == "error" for kind, _ in results), results
    assert all(
        isinstance(value, ResourceConflictError) for _, value in results
    ), results
    with app.app_context():
        assert app.config["TRANSFER_REPOSITORY"].list_for_seller(
            seed.seller.id
        ) == []
    assert _total_event_count(app) == 0


def test_concurrent_cancellations_record_single_audit_event(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _submitted_transfer(app, seed)

    def cancel():
        def operation():
            return _transfer_service(app).cancel_request(
                seed.seller.id, request_id, "concurrent cancel"
            )

        return operation

    results = _race(app, cancel(), cancel())

    for kind, value in results:
        assert kind in ("ok", "error"), results
        if kind == "error":
            assert isinstance(value, ResourceConflictError), results

    with app.app_context():
        stored = app.config["TRANSFER_REPOSITORY"].find_by_id(request_id)
    assert stored.status is TransferStatus.CANCELLED
    summaries = _events(app, request_id)
    _assert_valid_chain(summaries)
    assert [s[0] for s in summaries].count("TRANSFER_CANCELLED") == 1


def test_concurrent_approvals_record_single_audit_event(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _submitted_transfer(app, seed)

    def approve():
        def operation():
            return _transfer_service(app).approve_request(
                seed.registrar.id, request_id
            )

        return operation

    results = _race(app, approve(), approve())

    for kind, value in results:
        assert kind in ("ok", "error"), results
        if kind == "error":
            assert isinstance(value, ResourceConflictError), results

    with app.app_context():
        stored = app.config["TRANSFER_REPOSITORY"].find_by_id(request_id)
    assert stored.status is TransferStatus.APPROVED
    summaries = _events(app, request_id)
    _assert_valid_chain(summaries)
    assert [s[0] for s in summaries].count("TRANSFER_APPROVED") == 1


def test_concurrent_review_starts_record_single_audit_event(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _submitted_transfer(app, seed)

    def start_review():
        def operation():
            return _transfer_service(app).start_review(
                seed.registrar.id, Role.REGISTRAR, request_id
            )

        return operation

    results = _race(app, start_review(), start_review())

    for kind, value in results:
        assert kind in ("ok", "error"), results
        if kind == "error":
            assert isinstance(value, ResourceConflictError), results

    with app.app_context():
        stored = app.config["TRANSFER_REPOSITORY"].find_by_id(request_id)
    assert stored.status is TransferStatus.UNDER_REVIEW
    summaries = _events(app, request_id)
    _assert_valid_chain(summaries)
    assert [s[0] for s in summaries].count("TRANSFER_REVIEW_STARTED") == 1


def test_concurrent_cancel_and_approve_produce_single_valid_outcome(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _submitted_transfer(app, seed)

    def cancel():
        def operation():
            return _transfer_service(app).cancel_request(
                seed.seller.id, request_id, "concurrent cancel"
            )

        return operation

    def approve():
        def operation():
            return _transfer_service(app).approve_request(
                seed.registrar.id, request_id
            )

        return operation

    results = _race(app, cancel(), approve())

    for kind, value in results:
        assert kind in ("ok", "error"), results
        if kind == "error":
            assert isinstance(value, ResourceConflictError), results

    with app.app_context():
        stored = app.config["TRANSFER_REPOSITORY"].find_by_id(request_id)
    assert stored.status in (TransferStatus.APPROVED, TransferStatus.CANCELLED)

    summaries = _events(app, request_id)
    _assert_valid_chain(summaries)
    # The final state always matches the last audit event.
    assert summaries[-1][2] == stored.status.value
    # No duplicate audit events of any type.
    types = [summary[0] for summary in summaries]
    assert len(types) == len(set(types)), summaries
    assert types.count("TRANSFER_APPROVED") <= 1
    assert types.count("TRANSFER_CANCELLED") <= 1


# ---------------------------------------------------------------------------
# Section 4: ownership finalization concurrency
# ---------------------------------------------------------------------------


def test_repeated_confirmation_does_not_duplicate_buyer_ownership(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _pending_transfer(app, seed)
    service = _transfer_service(app, StubBlockchainGateway(seed.parcel_id))
    with app.app_context():
        first = service.finalize_transfer(
            seed.registrar.id, Role.REGISTRAR, request_id
        )
        second = service.finalize_transfer(
            seed.registrar.id, Role.REGISTRAR, request_id
        )

    assert first.status is TransferStatus.COMPLETED
    assert second.status is TransferStatus.COMPLETED
    _assert_single_finalization(app, seed, request_id)


def test_concurrent_finalization_applies_once_with_consistent_state(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _pending_transfer(app, seed)

    def finalize():
        def operation():
            return _transfer_service(
                app, StubBlockchainGateway(seed.parcel_id)
            ).finalize_transfer(seed.registrar.id, Role.REGISTRAR, request_id)

        return operation

    results = _race(app, finalize(), finalize())

    # Both attempts either complete idempotently or the loser is refused with
    # a conflict — never an unexpected failure, never a second application.
    for kind, value in results:
        assert kind in ("ok", "error"), results
        if kind == "ok":
            assert value.status is TransferStatus.COMPLETED, results
        else:
            assert isinstance(value, ResourceConflictError), results
    assert any(kind == "ok" for kind, _ in results), results

    # Exactly one applied finalization: status, ownership records, audit
    # event, and provenance all agree.
    _assert_single_finalization(app, seed, request_id)


@pytest.mark.filterwarnings("ignore::sqlalchemy.exc.SAWarning")
def test_failed_finalization_rolls_back_complete_transaction(pg_app):
    app = pg_app
    seed = _seed(app)
    request_id = _pending_transfer(app, seed)
    now = utc_now()

    with app.app_context():
        repository = app.config["TRANSFER_REPOSITORY"]
        request = repository.find_by_id(request_id)
        event = TransferAuditEvent(
            event_id="event-pg-rollback",
            request_id=request_id,
            event_type="OWNERSHIP_FINALIZED",
            actor_id=seed.registrar.id,
            actor_role=Role.REGISTRAR,
            from_status=TransferStatus.BLOCKCHAIN_PENDING,
            to_status=TransferStatus.COMPLETED,
            reason=None,
            created_at=now,
        )
        # Force an integrity failure at the very last write: the buyer's
        # ownership would collide with the existing seller row's primary key.
        with pytest.raises(InvalidInputError):
            repository.finalize_ownership(
                request,
                expected_status=TransferStatus.BLOCKCHAIN_PENDING,
                buyer_id=seed.buyer.id,
                buyer_ownership_id="ownership-pg-seller",
                event=event,
            )

        stored = repository.find_by_id(request_id)
        events = repository.list_audit_events(request_id)

    # Everything written before the failure was rolled back together.
    assert stored.status is TransferStatus.BLOCKCHAIN_PENDING
    assert stored.blockchain_status is BlockchainSubmissionStatus.SUBMITTED
    rows = _assert_ownership_invariants(app, seed.parcel_id)
    assert [row.owner_id for row in rows] == [seed.seller.id]
    assert rows[0].status is OwnershipStatus.ACTIVE
    assert not any(
        summary[0] == "OWNERSHIP_FINALIZED"
        for summary in [
            (
                row.event_type,
                row.from_status.value if row.from_status is not None else None,
                row.to_status.value,
            )
            for row in events
        ]
    )

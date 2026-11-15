# Backend API: Ownership Management

## Parcel Cadastral Numbers

Cadastral numbers are normalized by removing ASCII space, tab, line feed,
carriage return, vertical tab, and form-feed characters from both ends, then
converting the result to uppercase. The database unique index uses the same
edge-character set. Other Unicode whitespace is not trimmed by this policy.
The migration `e9c41a7b6d20` preflights existing cadastral values and refuses
to replace the older index when normalized duplicates exist; it does not
modify parcel records.

Ownership records are created by registrars using `POST /api/ownership`.
The request contains `ownership_id`, `parcel_id`, `owner_id`, `share`, and
`status`. Owners must be existing citizen accounts. Shares must be greater than
zero, at most 100, and have no more than six decimal places, matching the
database `NUMERIC(20, 6)` column.

Active shares for one parcel may not total more than 100%. Creating an active
record for an owner who already has an active record for that parcel is
rejected. The application validates this in the service and again inside the
persistence transaction. PostgreSQL transactions lock the parcel row while
checking the aggregate and inserting, and a partial unique index prevents
duplicate active parcel-owner records. SQLite ignores `SELECT ... FOR UPDATE`;
it is suitable for the functional tests but does not verify PostgreSQL's
concurrent-write behavior.

All three ownership read endpoints require authentication and allow citizens,
registrars, and administrators:

- `GET /api/parcels/{parcel_id}/ownership` returns every stored ownership row
  for compatibility.
- `GET /api/parcels/{parcel_id}/ownership/current` returns rows with status
  `ACTIVE`.
- `GET /api/parcels/{parcel_id}/ownership/history` returns rows with status
  `INACTIVE` or `DISPUTED`.

The history endpoint classifies existing ownership rows by status and orders
them by their creation timestamps. Existing rows do not contain a verified
transfer provenance or a dedicated ownership-event log, so this endpoint
does not claim to reconstruct legal ownership changes. No update, reassignment,
or deletion endpoint is exposed. Transfer approval does not automatically
change ownership; ownership changes must not be inferred from transfer status.

`GET /api/parcels/{parcel_id}/ownership/events` provides traceable
provenance for transfers this application actually finalized: parcel,
previous owner, new owner, related transfer request, finalization time, and
the verified blockchain transaction reference. Entries are derived only from
`COMPLETED` transfers, so no historical records are invented for legacy
ownership rows.

The migration `d6f1a3b9c240` checks existing active ownership data before
creating the partial unique index. It fails without modifying data if it finds
duplicate active parcel-owner rows or aggregate active shares above 100%.

## Transfer Management

Transfer requests are submitted by current citizen owners using
`POST /api/transfers` with `parcel_id` and `buyer_reference`. A buyer reference
may be the exact registered email address or user ID. The buyer must exist and
have the `CITIZEN` role. Both the service and the persistence transaction
verify that the parcel is `ACTIVE` and that the seller is its sole active owner
with a 100% share. Co-owned and partial-share transfers are not supported.

Submission resolves the buyer once and persists the canonical user ID as
`transfer.buyer_id` alongside the original `buyer_reference`, which is
retained unchanged for backward compatibility. Transfer access, registrar
review validation, ownership finalization, and ownership provenance use the
canonical ID when it exists, so buyer access and finalization keep working
after the buyer changes their email address. Transfer responses include an
additive `buyer_id` field (`null` for legacy records). Legacy records created
before this column keep the reference-based fallback: an unresolvable legacy
reference raises a clear error and is never silently reassigned to another
user. The `buyer_id` column is part of the schema contract and requires the
migration coordinated by Person 1; until it is applied, this backend must not
be deployed against an existing migrated database.

The existing endpoints remain:

- `GET /api/transfers` lists requests visible to the authenticated citizen,
  registrar, or administrator.
- `GET /api/transfers/{request_id}` returns a request and its audit history;
  citizens can read it only as seller or resolved buyer.
- `POST /api/transfers/{request_id}/cancel` is available to the seller while a
  request is cancellable. A registrar-approved request can be cancelled by its
  seller when blockchain status is `UNAVAILABLE`, `NOT_SUBMITTED`, or absent
  on a legacy request, releasing the parcel's active-transfer slot.
- `GET /api/registrar/transfers` lists the review queue (`SUBMITTED` and
  `UNDER_REVIEW` requests).
- `POST /api/registrar/transfers/{request_id}/review` starts a review:
  `SUBMITTED -> UNDER_REVIEW`, recording the reviewer, the review timestamp,
  and a single `TRANSFER_REVIEW_STARTED` audit event. Repeated starts are
  idempotent and never duplicate the event; any other state returns a
  conflict. The optional body accepts only `{"reason": "..."}`.
- `POST /api/registrar/transfers/{request_id}/approve` and
  `POST /api/registrar/transfers/{request_id}/reject` are registrar review
  operations; both work from `SUBMITTED` or `UNDER_REVIEW`. Rejection
  requires a reason.

Submission creates `SUBMITTED`; a registrar may start a review to move it to
`UNDER_REVIEW` before approving or rejecting it, and direct approval or
rejection from `SUBMITTED` remains supported. Approval is
not completion: approved requests remain `APPROVED` with blockchain status
`UNAVAILABLE`, no transaction hash, and no ownership changes. The seller may
cancel this approved request when no blockchain processing was started.
Rejected, cancelled, failed, and completed requests cannot be reopened.

Blockchain submission and confirmation come from the integration gateway
agreed with Person 1 (`BlockchainGateway` in `app/transfers/blockchain.py`,
injected through `app.config["BLOCKCHAIN_GATEWAY"]`). The built-in default is
an unavailable gateway that never submits a transaction and never returns a
confirmation, so nothing can be finalized until the real integration is
wired in. `POST /api/registrar/transfers/{request_id}/blockchain/submit`
moves an `APPROVED` request to `BLOCKCHAIN_PENDING` and stores the ledger
transaction reference; it never changes ownership.

Ownership changes only inside `TransferService.finalize_transfer`, which is
called by trusted server-side code, not by an HTTP client — no endpoint
accepts a client-supplied confirmation. Finalization reads the confirmation
from the gateway boundary, requires a verified confirmation matching the
stored transaction, revalidates buyer, seller, and parcel eligibility, and
then deactivates the seller's ownership, creates the buyer's ownership with
the preserved share, marks the request `COMPLETED`, and writes an
`OWNERSHIP_FINALIZED` audit event — all in one database transaction that
rolls back completely on failure. Repeated confirmation notifications are
idempotent and cannot create duplicate ownership records or duplicate events.

Submission locks the parcel row on PostgreSQL and validates ownership, parcel
status, and buyer role again in the same transaction that writes the request
and its audit event. The existing partial unique index
`uq_transfer_requests_one_active_per_parcel` is the final guard against
conflicting active requests. Status updates use compare-and-set semantics and
write their audit events in the same transaction. SQLite tests exercise the
functional and rollback behavior but do not validate PostgreSQL row-lock
concurrency.

## Testing

`python -m pytest -q` runs the whole backend suite: the SQLite-based unit and
integration tests plus the PostgreSQL concurrency tests.

`tests/test_postgres_concurrency.py` exercises real parallel transactions
against an isolated, disposable embedded PostgreSQL server provided by the
`pgserver` package (pinned in `requirements.txt`). The server listens on a
random localhost port with its own temporary data directory, which is removed
when the session ends; every test gets its own `CREATE DATABASE`, so no shared
or production database is ever touched and no migrations are applied. The
module is skipped automatically when `pgserver` is unavailable — SQLite
results are never treated as proof of PostgreSQL concurrency.

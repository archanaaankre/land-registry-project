# BlockchainGateway Integration Handover

**Audience:** Person 1 (BlockchainGateway owner).  
**Owner of this document:** Person 2 (ownership-finalization backend).  
**Source of truth:** the actual code in `D:\land-registry-project-main\backend`. Nothing here is invented; anything the code does not yet specify is flagged as "needs agreement."

> **Restrictions respected:** no blockchain functionality is implemented here, no existing source/test file was modified, no migrations were created or applied, no frontend code was touched, nothing was committed or pushed. The working tree was clean before this document was added.

---

## 1. What Person 2 owns (context)

- Parcel management, ownership management and provenance.
- Transfer request management.
- Buyer identity handling (canonical `buyer_id` resolved at submission; `buyer_reference` kept for legacy).
- Transfer review lifecycle (submit → under review → approve/reject → blockchain submit → finalize).
- Ownership finalization after trusted, verified blockchain confirmation.
- Audit and provenance handling (`OWNERSHIP_FINALIZED` audit event; `GET /api/parcels/{parcel_id}/ownership/events`).

Person 1 owns authentication, users/roles, admin, account activation/deactivation, smart contracts, the `BlockchainGateway` implementation, and shared migration coordination.

---

## 2. The exact function that receives trusted confirmation and finalizes ownership

### `TransferService.finalize_transfer`

File: `backend/app/transfers/services.py`  
Line: 528  
Signature:

```python
def finalize_transfer(self, actor_id: str, role: Role, request_id: str) -> TransferRequest
```

This is the **only** code path that reaches `TransferStatus.COMPLETED`. The state machine (`_ALLOWED_TRANSITIONS`, line 28) deliberately gives `BLOCKCHAIN_PENDING` an empty outgoing set and `COMPLETED` an empty outgoing set; the generic transition helper can never set `COMPLETED`.

### What it does, in order

1. **Authorization:** `role` must be in `TRANSFER_FINALIZE_ROLES` (`Role.REGISTRAR`, `Role.ADMIN`), otherwise `AuthorizationError` (403).
2. **Lookup:** `request_id` is validated (`validate_identifier`) and the row is loaded; missing → `ResourceNotFoundError` (404).
3. **Idempotent short-circuit:** if status is already `COMPLETED`, return the stored request immediately (repeated confirmation notification).
4. **State guard:** status must be `BLOCKCHAIN_PENDING`; otherwise `ResourceConflictError` (409). `blockchain_status` must be `PENDING` or `SUBMITTED`; otherwise conflict ("no submitted blockchain transaction to confirm").
5. **Fetch confirmation from the gateway only:** `confirmation = self._trusted_gateway().verify_confirmation(request.request_id)`. Callers can never supply a confirmation. If the gateway returns `None` → `ResourceConflictError` ("No verified blockchain confirmation exists for this transfer.").
6. **Match the confirmation to this transfer:** `confirmation.request_id`, `confirmation.parcel_id`, and `confirmation.tx_id` must equal the stored `request_id`, `parcel_id`, `blockchain_tx_id`; mismatch → `ResourceConflictError` ("The blockchain confirmation does not match this transfer.").
7. **Reject failure:** `confirmation.status == FAILED` → `ResourceConflictError` (uses `failure_reason`).
8. **Require verified finality:** `confirmation.status == CONFIRMED` **and** `confirmation.verified is True`; anything else (missing, unverified, `PENDING`) → `ResourceConflictError` ("The blockchain transaction is not verified as confirmed.").
9. **Re-validate eligibility inside the transaction:** parcel `ACTIVE`; buyer resolvable via canonical `buyer_id`, not the seller, has `CITIZEN` role; seller is the sole active owner with 100% share; buyer does not already hold an active ownership for the parcel.
10. **Atomically persist:** `repository.finalize_ownership(finalized, expected_status=BLOCKCHAIN_PENDING, buyer_id=..., buyer_ownership_id=..., event=event)` which, in one DB transaction:
    - locks the parcel row (`SELECT ... FOR UPDATE`),
    - compare-and-set updates the transfer to `COMPLETED` with `blockchain_tx_id` and `blockchain_status=CONFIRMED` (row-count check guards concurrent/duplicate finalization),
    - deactivates the seller's active ownership,
    - inserts the buyer's active ownership with the preserved share,
    - writes the `OWNERSHIP_FINALIZED` audit event,
    - commits; any failure rolls back everything.

### Authorization constant

File: `backend/app/transfers/authorization.py`

```python
TRANSFER_FINALIZE_ROLES = (Role.REGISTRAR, Role.ADMIN)
```

`Role` enum (`backend/app/models.py`): `CITIZEN = "CITIZEN"`, `REGISTRAR = "REGISTRAR"`, `ADMIN = "ADMIN"`.

---

## 3. Integration contract (what the gateway must implement)

The gateway is injected through `app.config["BLOCKCHAIN_GATEWAY"]` and must implement the `BlockchainGateway` protocol.

File: `backend/app/transfers/blockchain.py`

### Protocol

```python
class BlockchainGateway(Protocol):
    def submit(self, request: TransferRequest) -> BlockchainSubmission: ...
    def verify_confirmation(self, request_id: str) -> BlockchainConfirmation | None: ...
```

### `BlockchainSubmission` (returned by `submit`)

```python
@dataclass(frozen=True)
class BlockchainSubmission:
    request_id: str
    status: BlockchainSubmissionStatus
    tx_id: str | None = None
    failure_reason: str | None = None
```

`submit_to_blockchain` (services.py line 466) requires `status` to be `PENDING` or `SUBMITTED` and `tx_id` to be non-empty; `UNAVAILABLE` → `RegistryUnavailableError` (503); anything else → `ResourceConflictError` (409).

### `BlockchainConfirmation` (returned by `verify_confirmation`) — REQUIRED fields

```python
@dataclass(frozen=True)
class BlockchainConfirmation:
    request_id: str        # must equal the transfer's request_id
    parcel_id: str         # must equal the transfer's parcel_id
    tx_id: str             # must equal the stored blockchain_tx_id; must be non-empty
    status: BlockchainSubmissionStatus   # must be CONFIRMED
    verified: bool         # must be True
    confirmed_at: datetime
    failure_reason: str | None = None
```

`verified` is the flag the workflow trusts. It must only be `True` after the integration has independently read the transaction back from the ledger (receipt, chaincode event, or state proof) and matched it to this `request_id`/`parcel_id`. A status field alone is never sufficient proof of confirmation (stated in the module docstring).

### `BlockchainSubmissionStatus` enum

File: `backend/app/models.py` line 83

```python
NOT_SUBMITTED = "NOT_SUBMITTED"
PENDING     = "PENDING"
SUBMITTED   = "SUBMITTED"
CONFIRMED   = "CONFIRMED"
FAILED      = "FAILED"
UNAVAILABLE = "UNAVAILABLE"
```

### Default (until Person 1 wires the real gateway)

`UnavailableBlockchainGateway` (`backend/app/transfers/blockchain.py` line 69): `submit` returns `UNAVAILABLE`; `verify_confirmation` returns `None`. It never confirms anything, so finalization stays impossible until a real gateway is injected. `repository_bootstrap` (`backend/app/persistence/repositories.py` line 878) installs this default when `BLOCKCHAIN_GATEWAY` is not configured.

---

## 4. Answers to the 12 integration-contract points

### 1. Exact function or service method signature

`TransferService.finalize_transfer(actor_id: str, role: Role, request_id: str) -> TransferRequest`  
File: `backend/app/transfers/services.py`, line 528.

There is **no HTTP route** for finalization. `backend/app/routes.py` does not register `/.../finalize` or `/.../confirm`. The tests (`test_ownership_finalization.py` lines 733-745) confirm both `POST /api/registrar/transfers/{id}/finalize` and `POST /api/transfers/{id}/confirm` return 404. Finalization is reachable only at the service layer by trusted server-side code (or by a route Person 1/Person 2 may add later — needs agreement).

### 2. Required input parameters

| Parameter | Type | Notes |
|---|---|---|
| `actor_id` | `str` | The authenticated actor finalizing; recorded on the audit event. |
| `role` | `Role` | Must be in `TRANSFER_FINALIZE_ROLES` (`REGISTRAR`, `ADMIN`). |
| `request_id` | `str` | Validated transfer request identifier (`validate_identifier`). |

The confirmation itself is **not** an input parameter; it is always fetched from the gateway by `request_id`.

### 3. Required confirmation fields (`BlockchainConfirmation`)

| Field | Type | Requirement |
|---|---|---|
| `request_id` | `str` | Must equal `TransferRequest.request_id`. |
| `parcel_id` | `str` | Must equal `TransferRequest.parcel_id`. |
| `tx_id` | `str` | Must equal `TransferRequest.blockchain_tx_id`; must be non-empty. |
| `status` | `BlockchainSubmissionStatus` | Must be `CONFIRMED`. |
| `verified` | `bool` | Must be `True`. |
| `confirmed_at` | `datetime` | Present on the dataclass; not additionally validated by finalize beyond existence. |
| `failure_reason` | `str \| None` | Only surfaced when `status == FAILED`; otherwise not used. |

No other confirmation fields are read by `finalize_transfer`. Anything the gateway wants to send beyond these fields is not consumed by the current code — needs agreement if Person 1 wants to extend it (see §7-8).

### 4. Transaction hash requirements

- A `tx_id` is stored on the transfer as `blockchain_tx_id` (column `String(255)`, nullable) when `submit_to_blockchain` succeeds (`backend/app/transfers/services.py` line 511).
- At finalization, `confirmation.tx_id` must exactly match the stored `request.blockchain_tx_id` (services.py line 573). Mismatch → `ResourceConflictError`, state unchanged.
- The gateway's `submit` result must return a non-empty `tx_id` when status is `PENDING`/`SUBMITTED`; missing `tx_id` → `ResourceConflictError` ("The blockchain integration did not return a transaction reference.").
- At finalization, `blockchain_tx_id` is re-stored from `confirmation.tx_id` (services.py line 627) and `blockchain_status` set to `CONFIRMED`.

No format/length validation of the hash itself is applied beyond non-empty and matching; `String(255)` is the DB column bound. If Person 1 needs a specific hash format (e.g. `0x`-prefixed), that needs agreement.

### 5. Blockchain network / chain identifier requirements

**None present in the current interface.** `BlockchainConfirmation`, `BlockchainSubmission`, `BlockchainGateway`, and `TransferRequest` have no `chain_id`, `network_id`, `chain`, or comparable field. Multi-chain disambiguation is not handled. If Person 1 needs network/chain identification, the fields, matching logic, and any validation must be agreed and added — this is an open item, not something the code expects today.

### 6. Contract address requirements

**None present in the current interface.** No contract address field exists on the confirmation, submission, gateway protocol, or transfer model. If Person 1 needs contract-address binding/verification, that must be agreed and added — open item.

### 7. Confirmation / finality requirements

- `confirmation.verified is True` is mandatory.
- `confirmation.status == BlockchainSubmissionStatus.CONFIRMED` is mandatory.
- `verified` must only be set after independent ledger read-back (receipt / chaincode event / state proof) and match to this transfer — per the module docstring in `blockchain.py`.
- A `status` field alone is never sufficient proof.
- `FAILED` status is rejected outright (uses `failure_reason`).
- `PENDING`/`SUBMITTED`/`NOT_SUBMITTED`/`UNAVAILABLE` statuses are rejected at finalization (not a verified confirmation).
- Gateway returning `None` (no confirmation yet) → `ResourceConflictError`; callers may retry later when a confirmation exists.

### 8. Expected response format

`finalize_transfer` returns the `TransferRequest` domain object. The existing JSON transfer response shape (used by `_transfer_response` in `backend/app/routes.py` line 247) is:

```json
{
  "request_id": "string",
  "parcel_id": "string",
  "seller_id": "string",
  "buyer_reference": "string",
  "buyer_id": "string|null",
  "status": "COMPLETED",
  "reviewer_id": "string|null",
  "review_reason": "string|null",
  "reviewed_at": "ISO-8601|null",
  "blockchain_tx_id": "string",
  "blockchain_status": "CONFIRMED",
  "failure_reason": "string|null",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

The `OWNERSHIP_FINALIZED` audit event shape (`_audit_response`, routes.py line 270):

```json
{
  "event_id": "string",
  "request_id": "string",
  "event_type": "OWNERSHIP_FINALIZED",
  "actor_id": "string",
  "actor_role": "REGISTRAR",
  "from_status": "BLOCKCHAIN_PENDING",
  "to_status": "COMPLETED",
  "reason": "Ownership finalized after verified blockchain transaction <tx_id>.",
  "created_at": "ISO-8601"
}
```

Ownership provenance (`GET /api/parcels/{parcel_id}/ownership.events`) entry shape (`list_ownership_events`, services.py line 280):

```json
{
  "parcel_id": "string",
  "request_id": "string",
  "previous_owner_id": "string",
  "new_owner_id": "string",
  "finalized_at": "ISO-8601",
  "blockchain_tx_id": "string"
}
```

### 9. Validation and authorization requirements

**Authorization:**
- `role` in `{REGISTRAR, ADMIN}` (`TRANSFER_FINALIZE_ROLES`); else `AuthorizationError` (403).
- Citizens never reach the gateway and never change state (tests confirm).

**Pre-finalization validation (services.py, all raise before touching the gateway/state unless noted):**
- Transfer exists → else `ResourceNotFoundError` (404).
- Status == `BLOCKCHAIN_PENDING` → else `ResourceConflictError` (409).
- `blockchain_status` ∈ `{PENDING, SUBMITTED}` → else conflict.
- Confirmation not `None` → else conflict.
- Confirmation fields match the stored transfer → else conflict.
- Confirmation not `FAILED` → else conflict (uses `failure_reason`).
- Confirmation `status == CONFIRMED` and `verified == True` → else conflict.

**Inside the persistence transaction (`SqlAlchemyTransferRepository.finalize_ownership`, persistence/repositories.py line 654):**
- Parcel exists and is `ACTIVE` → else conflict/not found.
- Compare-and-set on `status == BLOCKCHAIN_PENDING`; if rowcount != 1:
  - if already `COMPLETED` with same `blockchain_tx_id` → idempotent return (duplicate finalization guard);
  - else `ResourceConflictError` (409).
- Seller is sole active owner, share == 100 → else conflict/authorization.
- Buyer exists, role `CITIZEN`, not the seller → else not found/invalid input.
- Buyer does not already hold an active ownership for the parcel → else conflict.
- Seller's active ownership deactivated; buyer's active ownership inserted with preserved share; audit event written; single commit with full rollback on any failure.

### 10. Error and retry behavior

| Situation | Error | HTTP code (via auth error handler) | State change? | Retry guidance |
|---|---|---|---|---|
| Wrong role | `AuthorizationError` | 403 | None | Do not retry; caller not authorized. |
| Missing transfer | `ResourceNotFoundError` | 404 | None | Do not retry with same id. |
| Not `BLOCKCHAIN_PENDING` / no submitted tx | `ResourceConflictError` | 409 | None | Do not retry; terminal or wrong state. |
| Gateway returns `None` | `ResourceConflictError` | 409 | None | **Safe to retry later** once a confirmation exists. |
| Confirmation mismatch | `ResourceConflictError` | 409 | None | Do not retry; gateway/transfer out of sync. |
| `FAILED` confirmation | `ResourceConflictError` | 409 | None | Do not retry; transaction failed. |
| Not `CONFIRMED` or `verified == False` | `ResourceConflictError` | 409 | None | Safe to retry later if confirmation not yet final. |
| No gateway injected | `RegistryUnavailableError` | 503 | None | Retry once the real gateway is configured. |
| DB failure mid-transaction | `DatabaseUnavailableError` / `InvalidInputError` | 503 / 400 | None (full rollback) | Safe to retry; nothing was persisted. |
| Concurrent finalization (CAS loser) | `ResourceConflictError` | 409 | None | Do not retry; another writer won. |

All mutating repository operations wrap `SQLAlchemyError` → rollback → `DatabaseUnavailableError` (503). `finalize_ownership` rolls back every change on any failure (tests confirm, e.g. `test_database_failure_rolls_back_all_finalization_changes`).

### 11. Idempotency behavior

Repeated confirmation notifications are idempotent:

1. Service layer: if `request.status == COMPLETED`, `finalize_transfer` returns the stored request immediately — no gateway call, no audit event, no ownership change (`test_repeated_confirmation_is_idempotent`).
2. Repository layer: `finalize_ownership` uses compare-and-set (`expected_status=BLOCKCHAIN_PENDING`). If two concurrent requests race, the loser gets rowcount == 0; if the row is already `COMPLETED` with the same `blockchain_tx_id`, it returns the stored row idempotently; otherwise `ResourceConflictError`.
3. Result: exactly one `OWNERSHIP_FINALIZED` audit event and exactly one active buyer ownership record, regardless of how many times confirmation is delivered.

### 12. How duplicate or invalid confirmations are handled

- **Duplicate (already COMPLETED):** short-circuited at the service layer before consulting the gateway; returns the stored `COMPLETED` request; no duplicate event or ownership record.
- **Invalid — no confirmation (`None`):** `ResourceConflictError`; state stays `BLOCKCHAIN_PENDING`; gateway `verified_requests` stays empty (tests confirm terminal states never consult the gateway). Safe to retry later.
- **Invalid — unverified / `PENDING` status / mismatch / `FAILED`:** `ResourceConflictError`; state stays `BLOCKCHAIN_PENDING`; no ownership change; no `OWNERSHIP_FINALIZED` event.
- **Invalid — terminal states (`REJECTED`, `CANCELLED`):** `finalize_transfer` raises `ResourceConflictError` **before** calling `verify_confirmation`, so the gateway is never consulted; state unchanged.

---

## 5. Task C — Transfer review role compatibility

### Current authorization (as-is; not modified)

| Concern | Constant / location | Authorized roles |
|---|---|---|
| Review queue (`GET /api/registrar/transfers`) | `TRANSFER_REVIEW_ROLES = (Role.REGISTRAR,)` — `authorization.py` line 6, route decorator line 337 | REGISTRAR only |
| Start review (`POST .../review`) | `TRANSFER_REVIEW_ROLES` (route line 345); service `start_review` allows `(REGISTRAR, ADMIN)` but route restricts to REGISTRAR | REGISTRAR only (via route) |
| Approve (`POST .../approve`) | `TRANSFER_REVIEW_ROLES` (route line 358); service `approve_request` has **no service-level role check** | REGISTRAR only (via route) |
| Reject (`POST .../reject`) | `TRANSFER_REVIEW_ROLES` (route line 371); service `reject_request` has **no service-level role check** | REGISTRAR only (via route) |
| Blockchain submit (`POST .../blockchain/submit`) | `TRANSFER_REVIEW_ROLES` (route line 386); service `submit_to_blockchain` allows `(REGISTRAR, ADMIN)` but route restricts to REGISTRAR | REGISTRAR only (via route) |
| Finalize (`finalize_transfer`) | `TRANSFER_FINALIZE_ROLES = (Role.REGISTRAR, Role.ADMIN)` — `authorization.py` line 9; **no HTTP route exists** | REGISTRAR and ADMIN (service level) |
| Read transfers | `TRANSFER_READ_ROLES = (CITIZEN, REGISTRAR, ADMIN)` | all three |

`Role` enum (`backend/app/models.py`): `CITIZEN`, `REGISTRAR`, `ADMIN`. There is **no `VERIFICATION_OFFICER` role** today.

### Does the existing review workflow authorize REGISTRAR?

Yes. REGISTRAR is the only role admitted through the route decorators for the review queue, start-review, approve, reject, and blockchain-submit endpoints (`TRANSFER_REVIEW_ROLES = (Role.REGISTRAR,)`). ADMIN is deliberately **not** authorized at the route level for these ordinary-transfer operations, although ADMIN is included in `TRANSFER_FINALIZE_ROLES` for finalization (service level only; no route).

### If the agreed workflow becomes

- **VERIFICATION_OFFICER: document verification** — this role does not exist in the `Role` enum or any authorization constant. Adding it is Person 1's role-management work. If added, the review/approve/reject/submit route decorators and service checks, plus `TRANSFER_FINALIZE_ROLES`, would need updating to include or exclude it as agreed. The DB check constraint `users.role IN ('CITIZEN','REGISTRAR','ADMIN')` (`persistence/models.py` line 52) would also need a migration (Person 1 coordinates migrations).
- **REGISTRAR: final approval or rejection** — REGISTRAR already holds approve/reject at the route level. No change needed for this part **unless** ADMIN is currently expected to also approve/reject (it is not, at the route level).
- **ADMIN: user and role administration, without ordinary transfer approval** — ADMIN already lacks ordinary-transfer approval at the route level (`TRANSFER_REVIEW_ROLES` is REGISTRAR only). One nuance: ADMIN **can** call `finalize_transfer` at the service level (`TRANSFER_FINALIZE_ROLES` includes ADMIN), but there is no HTTP route for finalization today. If "without ordinary transfer approval" is meant to also exclude ADMIN from finalization, `TRANSFER_FINALIZE_ROLES` would need to be changed to `(Role.REGISTRAR,)` — needs agreement between Person 1 and Person 2.

### Shared authorization / schema dependencies to flag for Person 1

1. `Role` enum — `CITIZEN`, `REGISTRAR`, `ADMIN` only. Adding `VERIFICATION_OFFICER` is Person 1's role work and cascades to every `TRANSFER_*_ROLES` constant, route decorator, service check, and the `users.role` DB check constraint (migration required).
2. `TRANSFER_REVIEW_ROLES` and `TRANSFER_FINALIZE_ROLES` in `backend/app/transfers/authorization.py`.
3. Route decorators `@roles_required(*...)` in `backend/app/routes.py` — these are the effective enforcement; service-layer checks are inconsistent (some endpoints rely solely on the decorator).
4. `BlockchainGateway` protocol and `BlockchainConfirmation`/`BlockchainSubmission` dataclasses in `backend/app/transfers/blockchain.py`.
5. `app.config["BLOCKCHAIN_GATEWAY"]` injection point (`routes.py` line 71; `repository_bootstrap` in `persistence/repositories.py` line 889 installs `UnavailableBlockchainGateway` by default).
6. Schema contract (migrations coordinated by Person 1):
   - `transfer_requests.buyer_id` (nullable `String(128)`, FK to `users.id`) — canonical buyer identity; `blockchain_tx_id` (`String(255)`), `blockchain_status` (`String(32)`), `failure_reason` (`Text`).
   - `transfer_audit_events` table (FK to `transfer_requests.request_id`).
   - `ownerships` partial unique index `uq_ownerships_one_active_owner_per_parcel` (one active owner per parcel).
   - `transfer_requests` partial unique index `uq_transfer_requests_one_active_per_parcel` (one active transfer per parcel).
   - `users.role` check constraint.

---

## 6. Items that still need agreement (do not implement)

1. Whether an HTTP route should be added for finalization (currently none exists; both candidate paths return 404 in tests).
2. Whether ADMIN should retain `finalize_transfer` authorization under the proposed workflow.
3. Whether a `VERIFICATION_OFFICER` role is added, and whether it participates in review/approval/finalization.
4. Whether `BlockchainConfirmation`/`BlockchainSubmission` should gain network/chain identifier and/or contract address fields (none exist today).
5. Whether `tx_id` should have a specific format/length validation beyond non-empty and `String(255)`.
6. Any extension of the confirmation contract beyond the fields actually consumed by `finalize_transfer` (§4.3).

---

## 7. Exact source and test files Person 1 should inspect

### Source files (backend/)

| File | Relevance |
|---|---|
| `app/transfers/services.py` | `TransferService.finalize_transfer` (line 528), `submit_to_blockchain` (line 466), `_ALLOWED_TRANSITIONS` (line 28), `list_ownership_events` (line 262). |
| `app/transfers/blockchain.py` | `BlockchainGateway` protocol, `BlockchainConfirmation`, `BlockchainSubmission`, `BlockchainSubmissionStatus` usage, `UnavailableBlockchainGateway`. This is the interface Person 1 implements. |
| `app/transfers/authorization.py` | `TRANSFER_FINALIZE_ROLES`, `TRANSFER_REVIEW_ROLES`, `TRANSFER_SUBMIT_ROLES`, `TRANSFER_READ_ROLES`. |
| `app/transfers/repositories.py` | `TransferRepository` protocol including `finalize_ownership`. |
| `app/persistence/repositories.py` | `SqlAlchemyTransferRepository.finalize_ownership` (line 654) — atomic finalization, CAS, idempotency guard; `SqlAlchemyOwnershipRepository.create_ownership` (line 269); `repository_bootstrap` (line 878) — installs the default unavailable gateway. |
| `app/persistence/models.py` | ORM models: `TransferRequestModel` (blockchain fields, indexes), `TransferAuditEventModel`, `OwnershipModel`, `UserModel` (role check constraint). |
| `app/models.py` | `Role`, `TransferStatus`, `BlockchainSubmissionStatus`, `OwnershipStatus`, `TransferRequest`, `TransferAuditEvent`, `utc_now`. |
| `app/registry/services.py` | `OwnershipService`, `ParcelService` used by finalization for eligibility re-checks. |
| `app/registry/authorization.py` | `PARCEL_MANAGE_ROLES`, `OWNERSHIP_RECORD_ROLES` (REGISTRAR only). |
| `app/routes.py` | Route registrations and `_transfer_service()` (injects `BLOCKCHAIN_GATEWAY`); note absence of a finalize route. |
| `app/auth/decorators.py` | `roles_required` enforcement used by routes. |
| `app/auth/errors.py` | Error types raised during finalization (`AuthorizationError`, `ResourceConflictError`, `RegistryUnavailableError`, etc.). |
| `app/config.py` | `BLOCKCHAIN_GATEWAY` is read from `app.config` (not a config class attribute; set at bootstrap/runtime). |

### Test files (backend/tests/)

| File | Relevance |
|---|---|
| `test_ownership_finalization.py` | The authoritative contract for finalization: happy path, seller/buyer ownership updates, audit event, provenance, rejection of unverified/failed/mismatched confirmations, idempotency, rollback, authorization, no-HTTP-endpoint (404) assertions, stub gateway pattern (`StubBlockchainGateway`). |
| `test_review_lifecycle.py` | Review start/approve/reject behavior and role authorization (`TRANSFER_REVIEW_ROLES` = REGISTRAR). |
| `test_transfer_requests.py` | Transfer submission, read/cancel authorization, role assertions (`TRANSFER_SUBMIT_ROLES`, `TRANSFER_READ_ROLES`, `TRANSFER_REVIEW_ROLES`). |
| `test_buyer_identity.py` | Canonical `buyer_id` handling during finalization (email change / reuse cannot redirect a transfer). |
| `test_postgres_concurrency.py` | Concurrent finalization and CAS/idempotency under real PostgreSQL. |
| `conftest.py` | Test app bootstrapping (empty file — configuration is inline per test file). |

### Baseline verification

`python -m pytest tests/test_ownership_finalization.py -q` → **28 passed**. The working tree was clean (`git status`: nothing to commit, working tree clean) before this documentation was added; no source or test file was modified.

---

**End of handover.** Person 1 should implement `BlockchainGateway` against the protocol in `app/transfers/blockchain.py` and inject it via `app.config["BLOCKCHAIN_GATEWAY"]`; `TransferService.finalize_transfer` will then drive ownership finalization from the gateway's verified confirmations.

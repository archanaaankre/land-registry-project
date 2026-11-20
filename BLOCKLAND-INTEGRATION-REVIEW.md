# BlockLand Integration Review — `origin/main` into `integration/person1-person2-nov17`

**Date:** 2026-11-19
**Reviewer role:** Senior backend security engineer / integration reviewer
**Mode:** READ-ONLY inspection. No checkout, merge, rebase, reset, pull, commit, staging, migration, database access, or test execution was performed.

---

## 1. Scope, method, and limitations

### Requested commands (all executed read-only)

- `git status --short`
- `git branch --show-current`
- `git --no-pager log --oneline -5`
- `git --no-pager log --oneline HEAD..origin/main`
- `git --no-pager diff --stat HEAD..origin/main`
- `git --no-pager diff --name-status HEAD..origin/main`

Additional read-only inspections used `git --no-pager show origin/main:<path>`, `git --no-pager grep ... origin/main`, `git --no-pager ls-tree`, `git merge-base`, and `git diff origin/main -- <path>` to compare the incoming commit with the **working tree** for locally modified files. No `git diff` was run with a mode that changes files.

### Important interpretation limitation

`git diff HEAD..origin/main` compares **committed** `23d63e7` with committed `8830193`. It does **not** include the substantial uncommitted local work in the working tree. To avoid a misleading conclusion, the incoming document-integrity and RBAC files were additionally compared against the working tree using `git diff origin/main -- <path>`.

### Other limitations

- No automated tests were run. Running pytest/npm would create cache/bytecode files, which the safety rules prohibit. Test references below are based on inspecting test **definitions**, not execution results.
- A passing test is not treated as proof of security anywhere in this report.
- No migrations were run and no database was contacted. Alembic topology findings are static.
- No credentials, JWT secrets, tokens, or environment values were printed or reproduced. Hard-coded non-random test secrets in the incoming branch are referred to generically, never quoted.

---

## 2. Git context

| Item | Value |
|---|---|
| Current branch | `integration/person1-person2-nov17` |
| Current commit | `23d63e7` |
| Incoming branch | `origin/main` |
| Incoming commit | `8830193` |
| Merge base | `c7ae307` |
| Commits in `HEAD..origin/main` | 1 (`8830193`) |

`origin/main` is a single commit ahead of `c7ae307` on the Person 2 line of development. The current branch is a merge commit combining that line with Person 1 work (`7bf9f83`). Consequently, many items shown as “deleted” by `git diff HEAD..origin/main` are actually **Person 1 features that `origin/main` never received**, not deliberate removals by the incoming author. They must nevertheless be rejected as incoming changes because integrating `origin/main` wholesale would lose them.

Working tree status (preserved, not modified by this review):

- Modified: `backend/.env.example`, `backend/app/auth/errors.py`, `backend/app/config.py`, `backend/app/document_integrity/service.py`, `backend/app/routes.py`, `backend/app/transfers/services.py`, several backend test files, `frontend/src/pages/DocumentIntegrity.jsx`, `frontend/src/services/documentService.js`, `frontend/src/services/evaluationService.js`.
- Untracked: `backend/.venv-pgtest/`, `backend/tests/test_document_integrity.py`, `backend/tests/test_transfer_workflow_roles.py`, `package-lock.json`.

---

## 3. Executive verdict

**Do not integrate `origin/main` wholesale.**

The incoming commit contains several **technically strong additions** (durable admin audit events, guarded/locked last-active-Admin mutations, registrar ownership-creation UI, Verification Officer dashboard links). Those should be retained.

It also contains **security regressions that must be rejected**:

1. Fail-closed JWT secret validation and test-config support were removed.
2. Authorization now trusts the JWT `role` claim instead of the current database role, so revoked privileges remain usable until token expiry.
3. The initial Admin creation utility was deleted without replacement.
4. The migration chain was rewritten incompatibly with the current branch, with a broken `create_check_constraint()` call and a missing `buyer_id` column migration.
5. Multiple security regression tests were deleted or weakened.

Additionally, the incoming branch does **not** contain the locally implemented owner-approved Document Integrity policy, citizen-scoped reads, trusted-hash role restriction, or supporting-document upload action. Those local changes must be preserved.

---

## 4. Requirement-by-requirement assessment

### 4.1 Authentication and authorization

| Requirement | Incoming status | Evidence / note |
|---|---|---|
| JWT signature and expiration validated | **PASS (code), NOT VERIFIED by execution** | `backend/app/auth/service.py` is unchanged by the incoming commit. |
| Missing/insecure JWT secret rejected in production | **FAIL — Critical** | `backend/app/config.py:13` sets `JWT_SECRET_KEY` to fall back to `SECRET_KEY`, whose default is a known placeholder. `backend/app/__init__.py:14` removes `test_config` and the `validate_jwt_secret()` startup call. `backend/conftest.py` is emptied. |
| Test configuration support remains functional | **FAIL — High** | `create_app()` no longer accepts `test_config`; local tests that rely on it would break. |
| Deactivated accounts cannot log in | **PASS with caveat** | `backend/app/auth/api_service.py:107` rejects inactive users. Caveat: the message reveals account status (`Account is deactivated.`), which leaks existence/state. |
| Deleted accounts cannot use old JWTs | **PASS** | `backend/app/auth/decorators.py:72-75` rejects a token whose user no longer exists. |
| Current DB role checked on protected requests | **FAIL — Critical** | `backend/app/auth/decorators.py:41` uses `Role(claims["role"])`, and `:62-64` explicitly documents that the role is *not* re-read from the database. A demoted user keeps elevated access until token expiry. |
| Admin cannot promote to ADMIN | **PASS** | `backend/app/auth/api_service.py:35` `ADMIN_ASSIGNABLE_ROLES` excludes `ADMIN`; `:227` rejects it. |
| Only authorized roles access protected endpoints | **PARTIAL** | Route decorators remain, but because the role comes from the JWT claim, the role check is not fail-closed against revocation. |

### 4.2 Admin management

| Requirement | Incoming status | Evidence / note |
|---|---|---|
| Initial Admin creation continues working | **FAIL — Critical** | `backend/create_initial_admin.py` is deleted; no replacement creation path exists in `origin/main` (`git grep` found no `create_initial_admin` references). |
| Admin cannot deactivate own account | **PASS** | `backend/app/auth/api_service.py:261` self-deactivation check. |
| Last active Admin cannot be demoted/deactivated | **PASS (code), NOT VERIFIED by execution** | `backend/app/persistence/repositories.py:178,193` guarded mutations with row locks and re-check; `test_admin_concurrency.py` exists for PostgreSQL but was not run. |
| Concurrent admin mutations cannot bypass protection | **PASS (code), NOT VERIFIED by execution** | Same guarded mutation; disposable `pgserver` concurrency tests added but not executed in this review. |
| Guarded repository methods used consistently | **PASS for service path** | `AuthApiService` calls `..._with_admin_guard` methods. Unguarded `update_user_role`/`update_user_active_status` remain at `repositories.py:162,297` but are not used by routes. Latent risk only. |
| Durable audit records tied to mutation transaction | **PASS (code), NOT VERIFIED by execution** | New `backend/app/auth/audit.py`; audit row inserted via factory inside repository transaction; `test_admin_audit_persistence.py` covers rollback/atomicity. |
| Audit records contain no secrets | **PASS (code), NOT VERIFIED by execution** | `AdminAuditEventModel` has only identifiers/roles/event type/transitions/timestamp; test asserts no password/hash strings. |

### 4.3 Document Integrity — owner-approved policy

| Requirement | Incoming status | Evidence / note |
|---|---|---|
| ADMIN: view all, verify; no upload, no trusted-hash creation | **FAIL** | Incoming document routes still allow all four roles on `POST /api/documents/hash` (`origin/main:backend/app/routes.py`, `store_document_hash` decorator). No upload endpoint exists. |
| REGISTRAR: all document actions | **PARTIAL** | Can create trusted hashes and verify, but no supporting-upload action. |
| VERIFICATION_OFFICER: view all, upload, verify; no trusted hashes | **FAIL** | Currently can create trusted hashes; no upload action. |
| CITIZEN: scoped view/verify, upload only | **FAIL** | Incoming still allows citizen trusted-hash creation for owned parcels; no citizen-scoped list/detail; no upload action. |
| Only REGISTRAR creates trusted baselines | **FAIL** | Not implemented in incoming branch. |
| Supporting documents durably stored/retrievable | **NOT IMPLEMENTED (both branches)** | Incoming has no upload endpoint. Local non-persisting upload returns a calculated hash only. |
| SHA-256 verification not presented as legal proof | **PASS** | Disclaimer present in `frontend/src/services/evaluationService.js` on the incoming branch. |

The incoming branch does not modify document files relative to committed `23d63e7`; therefore this is an **absence of the locally implemented policy**, not a conflicting edit. Retain the working-tree document files.

### 4.4 Transfer workflow

| Requirement | Incoming status | Evidence / note |
|---|---|---|
| Citizen submits transfers | **PASS** | `backend/app/transfers/*` unchanged; `TRANSFER_SUBMIT_ROLES = (CITIZEN,)`. |
| VO verifies supporting documents | **NOT IMPLEMENTED** | No distinct supporting-document verification workflow exists. |
| Registrar reviews/approves/rejects | **PASS** | Authorization constants unchanged; routes unchanged. |
| Ownership finalization disabled, no client confirmation route | **PASS** | No finalize/confirm route in incoming `routes.py`; `finalize_transfer()` remains service-only with no caller. |
| No automatic ownership change on approval | **PASS** | Transfer service unchanged. |

Regression: incoming `backend/tests/test_transfer_requests.py` **deletes** `test_non_registrar_cannot_access_registrar_review_endpoints`, removing a useful 403 assertion for VO/Admin against reviewer endpoints. Restore it.

### 4.5 Frontend

| Incoming change | Assessment |
|---|---|
| New `frontend/src/pages/OwnershipCreate.jsx`, `ownershipService.js`, `ownershipValidation.js`, `ownershipValidation.test.js`, route `/registrar/ownership`, nav item | **Technically correct / retain.** Registrar-only route guard; backend `POST /ownership` is Registrar-only; client validation and tests are coherent. |
| `Dashboard.jsx` removes `canBrowseRegistry` restriction so VO sees parcel/evaluation links | **Correct / retain.** Matches backend read roles. |
| `adminService.js` changes `data.items` → `data.users` | **Correct only as a pair** with incoming backend `GET /api/admin/users` response shape (`routes.py:462`). If backend admin changes are taken without this line, admin user listing breaks. |
| Deletes `AdminUsers.jsx`, `AdminUsers.css`, `adminUserService.js` | **Acceptable.** These were unrouted duplicate/dead code. |
| Removes nested `registryReadRoles` wrapper in `App.jsx` | **No effective role change** (all four roles were already allowed). Slight loss of UI defense-in-depth only; backend still enforces. |
| README documents `npm test` and ownership checks | **Correct / retain.** |

---

## 5. Migration topology (static)

Incoming `backend/migrations/versions/` contains 8 revisions:

`a8a1c8b2698b` → `2f14c6a90b31` → `c31e8f4a2d70` → `d6f1a3b9c240` → `e9c41a7b6d20` → `f4a2b9c1d6e3` → `a7b8c9d0e1f2` → `c3a7e5f901b4` (single head `c3a7e5f901b4`).

Problems:

1. **Divergent head.** The current branch head is `c9d0e1f2a3b4`, which is **absent** from incoming. A database stamped `c9d0e1f2a3b4` cannot be upgraded with only incoming scripts; Alembic will report a missing revision. A merge revision is required.
2. **`buyer_id` migration deleted.** `b7e5c4d2a910` is deleted, yet `backend/app/persistence/models.py` on `origin/main` still declares `TransferRequestModel.buyer_id`. A fresh database built from the incoming migration chain will lack the column, breaking transfer submission/finalization code paths that read/write it.
3. **Broken `f4a2b9c1d6e3`.** At lines 22-25 and 31-33, `batch_op.create_check_constraint()` is called with the SQL expression as the first positional argument and `name=` as a keyword. The Alembic batch API signature is `create_check_constraint(constraint_name, condition, **kw)`. This will raise a `TypeError` at migration time.
4. **No server default for `is_active`.** `f4a2b9c1d6e3:18-20` adds `is_active` as `NOT NULL` with only a Python-side `default=True`. On a populated PostgreSQL table this will fail without a `server_default`, unlike the current branch's defensive migration.
5. **Non-defensive `a7b8c9d0e1f2`.** The incoming rewrite uses a plain `op.create_table("document_hashes", ...)`. On any database that already has that table (including the current branch's DB), upgrade fails.
6. **Deleted defensive/merge revisions.** `c4b73a19d620`, `d9f36b2a1c84`, `b7e5c4d2a910`, `f6b6ebf8c7d9`, `c9d0e1f2a3b4` are removed. These are required for upgrade-from-branched-history safety.

**No migration was run in this review.**

---

## 6. Test-suite changes

### Added by incoming (retain, adapt where needed)

- `backend/tests/test_active_user_authorization.py` — active/inactive/deleted account behavior. Important: it explicitly asserts that the JWT role claim remains authoritative; that assertion must be changed if the DB-role recheck is restored.
- `backend/tests/test_admin_audit_persistence.py` — audit atomicity and no-secret assertions.
- `backend/tests/test_admin_concurrency.py` — real PostgreSQL concurrency for last-admin protection.
- `backend/tests/test_admin_security.py` — role allowlist, self-deactivation, last-admin protection.
- `frontend/src/services/ownershipValidation.test.js` — pure validation tests.

### Deleted or weakened (reject)

- `backend/tests/test_config.py` — removed all JWT-secret validation tests.
- `backend/tests/test_initial_admin.py` — removed initial-admin tests.
- `backend/tests/test_admin_user_management.py` — removed; replaced by new admin tests, but loses some endpoint-level coverage.
- `backend/tests/test_auth_api.py` — removed DB-role recheck, inactive-token, and fail-closed lookup tests.
- `backend/tests/test_auth_foundation.py` — removed VO access, old-token DB role, role promotion, inactive/deleted token, and fail-closed tests.
- `backend/tests/test_registry_api.py` — weakened read-role policy assertions.
- `backend/tests/test_transfer_requests.py` — removed non-registrar reviewer-endpoint 403 test.

Incoming test fixtures use hard-coded non-random secrets that only work because validation was removed. Restoring validation requires updating those fixtures to generate valid random secrets locally.

---

## 7. Retain / Reject / Modify

### Retain (technically correct additions)

| Area | Incoming item |
|---|---|
| Admin audit | `backend/app/auth/audit.py`; `AdminAuditEventModel`; audit-event factory injection; audit rollback tests |
| Admin hardening | `ADMIN_ASSIGNABLE_ROLES`; self-deactivation block; `_guarded_admin_mutation` with row locks and re-check |
| Frontend | Ownership creation page/services/validation/tests and registrar route/nav item; VO dashboard links; `adminService.js` response shape (paired with backend) |
| Docs | Frontend README updates for `npm test` and ownership workflow |

### Reject (must not be integrated)

| Area | Incoming item |
|---|---|
| JWT secrets | `config.py:13` fallback to `SECRET_KEY`; removal of `validate_jwt_secret`; `create_app()` without `test_config`; emptied `conftest.py` |
| Authorization source | `decorators.py:41,55-64` JWT role claim as authority and no DB role re-read |
| Initial admin | Deletion of `backend/create_initial_admin.py` with no replacement |
| Migrations | Deletion of `c4b73a19d620`, `d9f36b2a1c84`, `b7e5c4d2a910`, `f6b6ebf8c7d9`, `c9d0e1f2a3b4`; broken `f4a2b9c1d6e3`; non-defensive `a7b8c9d0e1f2` |
| Tests | All deleted/weakened security tests listed in section 6 |
| Document policy | Any incoming state that would replace the local document-integrity implementation (incoming actually lacks it) |
| Docs | Deletion of `SECURITY-REVIEW.md` (low, but unnecessary) |

### Modify before integration

1. Add a **new Alembic merge revision** joining current head `c9d0e1f2a3b4` with incoming head `c3a7e5f901b4`. Do not delete existing history.
2. Restore/re-add the `buyer_id` migration (or fold it into a forward migration) so fresh databases match the model.
3. Fix `f4a2b9c1d6e3` `create_check_constraint()` calls to the batch signature `create_check_constraint(constraint_name, condition)`, and add `server_default` for `is_active`.
4. Restore `validate_jwt_secret()` and startup validation; keep `create_app(test_config)`; regenerate random secrets in test fixtures.
5. Restore DB role recheck in `roles_required`; decide a consistent status code for inactive accounts (current local behavior/tests use 401 `invalid_token`; incoming uses 403).
6. Make inactive-login errors generic to avoid account-state leakage.
7. Re-add the deleted regression tests and update the incoming tests that assert JWT-role authority.
8. Keep the local Document Integrity policy files and add the durable supporting-document storage design as a separate, explicitly scoped task.
9. If admin backend changes are integrated, also take `adminService.js:14` so response shape stays compatible.

---

## 8. Conflict inventory with local uncommitted work

| Local worktree file | Incoming modification | Integration note |
|---|---|---|
| `backend/app/config.py` | Yes (JWT validation removed) | **Direct conflict.** Retain local validation + upload-size config; reject incoming fallback. |
| `backend/app/routes.py` | Yes (admin routes rewritten) | **Direct conflict.** Merge admin route additions with local document-role restrictions and upload route. |
| `backend/app/auth/errors.py` | Yes (`AdminPromotionNotAllowedError` removed) | Retain local `PayloadTooLargeError`; decide whether to restore the promotion-specific error for clearer 403 semantics. |
| `backend/app/document_integrity/service.py`, `frontend/src/pages/DocumentIntegrity.jsx`, `frontend/src/services/documentService.js`, `frontend/src/services/evaluationService.js`, `backend/tests/test_document_integrity.py`, `backend/tests/test_transfer_workflow_roles.py` | No incoming changes | Retain local versions as-is. |
| `backend/app/transfers/services.py` | No incoming changes | Retain local service-level role checks. |
| `backend/.env.example` | No incoming changes | Retain local JWT guidance. |

Because these changes are uncommitted, any integration workflow must first preserve them (for example by committing them on the current branch) before applying or cherry-picking incoming commits. **This review did not do so.**

---

## 9. Features not verifiable in this read-only review

- Runtime behavior of the incoming application (no app started).
- Actual test results for incoming tests (no tests executed).
- Real PostgreSQL concurrency behavior (no database used).
- Whether the incoming admin audit transaction works against a shared database schema (no migrations applied).
- Whether the current Alembic version table is stamped `c9d0e1f2a3b4` in any live environment (no DB queried).
- Live HTTP status codes and frontend rendering.

---

## 10. Final recommendation

**Reject a wholesale merge/fast-forward of `origin/main`.** Build an integration patch that starts from the current branch (with all local work preserved), then selectively applies the retained items from section 7, restores the rejected security controls and tests, and adds a proper migration merge revision.

Priority order:

1. Restore JWT secret validation, `create_app(test_config)`, DB-role recheck, and initial Admin creation.
2. Resolve migration topology and the `buyer_id`/`f4`/`a7` defects without touching any shared database.
3. Preserve the local Document Integrity RBAC implementation and add durable supporting-document storage as a separate design task.
4. Integrate admin audit + guarded mutations + ownership UI.
5. Restore deleted/weakened tests and update incoming fixtures to valid random secrets.
6. Only then run the full safe backend suite, frontend lint/build/tests, and static migration-head check.

No finalization route or client-driven ownership finalization should be introduced at any point.

**Integration readiness verdict: NOT READY for direct integration; READY for selective cherry-pick after the modifications above.**

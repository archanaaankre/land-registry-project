# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Manual frontend workflow checks

The frontend has no automated test runner or test suite. These checks are for a controlled end-to-end environment using the existing Flask API. They are not live test results. Never create or modify records without authorization, and use only disposable test data and accounts.

### Preconditions

1. Start the existing Flask API separately and confirm it is reachable using the health endpoint documented for that deployment. The frontend does not call the health endpoint.
2. Set `VITE_API_BASE_URL` in the frontend environment to the existing API base (for example, a local API base ending in `/api`), then start the frontend with `npm run dev`.
3. Prepare an authorized citizen account, an authorized registrar account, and a parcel/transfer specifically approved for testing. Do not use real registry records.
4. Open browser developer tools and use the Network panel to verify request methods, paths, bodies, response status, and response data. Redact tokens and personal data from any notes.

### API surface expected by the current frontend

All paths below are relative to `VITE_API_BASE_URL`. Authenticated service calls use the current bearer token. The response descriptions are the fields the frontend validates or reads; they are not a request to change the API contract.

| Method and path | Request body | Frontend expectation |
| --- | --- | --- |
| `POST /auth/register` | `{ name, email, password, role: "CITIZEN" }` | Response contains `access_token`, `token_type: "Bearer"`, and `user` with a string `id` and supported `role`. |
| `POST /auth/login` | `{ email, password }` | Same token and user fields as registration. |
| `GET /auth/me` | None | Response contains `user` with a string `id` and supported `role`. |
| `GET /parcels` | None | Response contains an `items` array. |
| `GET /parcels/{parcelId}` | None | Response contains `parcel` with string `parcel_id`. |
| `GET /parcels/{parcelId}/ownership` | None | Response contains an `items` array. |
| `GET /transfers` | None | Response contains an `items` array. |
| `POST /transfers` | `{ parcel_id, buyer_reference }` | Response contains `transfer` with a non-empty `request_id` and `status`. |
| `GET /transfers/{requestId}` | None | Response contains a matching `transfer` with `request_id` and `status`, and a `history` array. |
| `POST /transfers/{requestId}/cancel` | `{ reason }` in the current page flow | Response contains a matching `transfer` with `request_id` and `status`. |
| `GET /registrar/transfers` | None | Response contains an `items` array. The review page reads `request_id`, `status`, `parcel_id`, `seller_id`, `buyer_reference`, and `created_at` from each item. |
| `POST /registrar/transfers/{requestId}/approve` | No body in the current page flow | Response contains a matching `transfer` with `request_id` and `status`. |
| `POST /registrar/transfers/{requestId}/reject` | `{ reason }` | Response contains a matching `transfer` with `request_id` and `status`. |

The evaluation dashboard’s ownership traceability reads the parcel list and each parcel’s ownership endpoint above. Its optional API latency sample makes five sequential authenticated `GET /auth/me` requests and five sequential authenticated `GET /parcels` requests. These are browser API response-time samples only—not transfer-processing or blockchain-confirmation measurements.

### Reproducible test cases

For each case, record **Pass**, **Fail**, or **Blocked**, the test account role, and the observed HTTP status/result. Never record credentials, tokens, or unnecessary personal data.

#### Authentication and routing

- [ ] **AUTH-1 — Citizen registration:** With an authorized test email, submit valid name, email, and password on `/register`. Verify the Network request is `POST /auth/register` with `role: "CITIZEN"` and that the UI enters the authenticated workspace only after a valid token/user response. Use a disposable account.
- [ ] **AUTH-2 — Sign-in and invalid credentials:** Sign in with an authorized test account and verify `POST /auth/login` uses `{ email, password }`. Repeat with deliberately invalid test credentials; confirm the API error is shown and protected content is not loaded.
- [ ] **AUTH-3 — Session check and protected routes:** With a valid stored test session, verify `GET /auth/me` and access to protected pages. Sign out, then directly open `/dashboard`, `/parcels`, `/transfers`, and `/registrar/transfers`; protected content must not be exposed and the user must be redirected to sign in.
- [ ] **AUTH-4 — Role restriction and expiry:** As a citizen, verify registrar navigation is absent and `/registrar/transfers` is denied/redirected. As a registrar, verify the review route is accessible. Test an expired/invalid test token; verify sign-out/redirect behavior and no false loaded state. Frontend role checks do not replace backend authorization.
- [ ] **AUTH-5 — Sign-out:** Sign out and verify the stored client token is cleared and protected views are no longer available.

#### Citizen parcel and transfer workflow

- [ ] **CIT-1 — Parcel list:** As a signed-in citizen, load `/parcels`. Verify `GET /parcels`, a loading state, API-backed parcel entries, and the true empty state for an empty `items` array. Cause a controlled read failure and verify an error/retry state, not a successful empty list.
- [ ] **CIT-2 — Parcel details:** Open a parcel returned by the API. Verify the detail request uses its actual ID and ownership history comes from `GET /parcels/{parcelId}/ownership`. Check missing records separately from request failures. Do not infer legal title beyond the returned records.
- [ ] **CIT-3 — Submit request:** Using only an authorized disposable test parcel, submit a buyer reference supported by the existing API. Verify `POST /transfers` sends exactly `parcel_id` and `buyer_reference`. Success must appear only after the API returns a transfer with a non-empty ID and status. Do not repeat this against real data.
- [ ] **CIT-4 — Validation and duplicate prevention:** Try submitting without a parcel, buyer reference, or ownership confirmation; verify client validation and no POST. During a deliberately delayed disposable-test submission, verify the submit button is disabled and no second POST is sent.
- [ ] **CIT-5 — Request list and detail:** Verify `GET /transfers`, list refresh, and navigation to `GET /transfers/{requestId}`. Confirm the returned request ID matches the requested ID and history is an array. Verify status/history reflect the API; malformed or failed responses must not appear as valid empty results.
- [ ] **CIT-6 — Failure handling:** In the controlled environment, exercise an API validation error, unavailable service, and a network failure. Verify the operation-specific error is visible, no success message appears, and the UI does not invent a request.
- [ ] **CIT-7 — Buyer lookup limitation:** Test only with approved buyer-reference data. The existing API may not find every buyer reference (including email-based references); record a not-found/empty result as a backend limitation. Do not infer or synthesize a request, or change the identifier/payload to work around it.

#### Registrar review

- [ ] **REG-1 — Review queue:** Sign in with an authorized registrar and verify `GET /registrar/transfers` populates the queue with API-returned items. Confirm loading, empty, and operation-specific error states.
- [ ] **REG-2 — Request details:** Open an eligible disposable request and verify `GET /transfers/{requestId}` returns matching details and a history array. Only requests in statuses the page supports (`SUBMITTED` or `UNDER_REVIEW`) should offer review actions.
- [ ] **REG-3 — Approve:** For an authorized disposable test request only, confirm and verify `POST /registrar/transfers/{requestId}/approve` (no body in the current page flow). After a successful response, verify the displayed details reload from the API and show the returned status.
- [ ] **REG-4 — Reject:** For a separate authorized disposable test request, enter a non-empty reason and verify `POST /registrar/transfers/{requestId}/reject` sends `{ reason }`. Confirm the response-driven status/history appears after reload.
- [ ] **REG-5 — Review failure:** Cause an authorized controlled review request to fail. Verify the error is shown and the request is not presented as approved, rejected, or completed unless the API subsequently reports that result.
- [ ] **REG-6 — Duplicate action prevention:** While an action is pending, verify review controls are disabled and repeated submissions do not issue duplicate requests.

#### Status integrity and evaluation

- [ ] **STATUS-1 — Distinct stages:** Verify the API-reported request submission, registrar decision, blockchain fields, and ownership records remain distinct. Registrar approval alone must never be described as blockchain submission/confirmation or completed ownership transfer.
- [ ] **STATUS-2 — Unsupported blockchain workflow:** Blockchain submission and confirmation are unavailable in this build. Verify the UI does not invent transaction IDs, block numbers, confirmation times, or ownership updates.
- [ ] **EVAL-1 — Honest measurements:** Verify unavailable tamper-detection, document-integrity, access-control test, transaction, and blockchain metrics remain unavailable/not measured rather than fabricated. If API sampling is run, confirm its requests are only `GET /auth/me` and `GET /parcels` and are labeled as API response latency.
- [ ] **EVAL-2 — Ownership traceability:** Verify entries come from actual parcel/ownership API responses and are not described as transfer events, proof of legal ownership, or blockchain confirmations.

### Known blockers and safety limits

- The existing Flask API must be running and reachable before live integration cases can pass.
- Testing requires authorized citizen and registrar accounts. Registration and review tests must use specifically approved accounts.
- Cases that submit, cancel, approve, or reject requests require authorization and disposable test records. Do not mutate production or real registry data.
- Buyer-reference lookup remains limited by the existing API. The frontend must not compensate with guessed identifiers, inferred records, or a changed payload.
- Blockchain submission and confirmation are unavailable. Do not equate registrar approval with blockchain confirmation or ownership transfer completion.
- No fake data or evaluation results may be used as evidence. Manual checks remain unexecuted until someone records actual outcomes from the running integration environment.

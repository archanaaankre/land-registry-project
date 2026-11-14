# BlockLand Authentication and Admin Security Review

## Finding

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | HIGH | `backend/app/config.py` | 12-13 | The application silently uses a fixed JWT signing-key fallback when no deployment secret is configured. A known signing key can allow forged JWTs, including tokens for an administrator, exposing admin user-management operations. | 8/10 |

### Evidence and impact

JWT issuance and validation use the configured key in `backend/app/auth/service.py` and `backend/app/auth/decorators.py`. Admin user-management endpoints rely on that JWT authentication in `backend/app/routes.py`. Authorization checks the account's current database role, but this does not protect against a forged token for an existing administrator account.

The risk applies when deployment leaves the key unset or uses a known placeholder. No secret values are reproduced in this report.

### Recommended remediation

Require an explicitly supplied, high-entropy JWT signing key and fail application startup if it is missing or matches a known placeholder. Remove the fixed fallback. Ensure deployment configuration and secret rotation are handled outside source control.

## Verification notes

- Backend: `158 passed` using the existing backend virtual environment.
- Frontend: `npm run lint` passed.
- Frontend: `npm run build` passed.
- The existing tests cover 403 responses for Citizen, Registrar, and Verification Officer requests to Admin endpoints. An unauthenticated request directly to each Admin endpoint was not explicitly covered by those tests.
- No application secrets, tokens, or database credentials are included here.

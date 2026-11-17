# CareRank 4.0 changelog

Based on merged CareRank 3.1, PR #3, latest `main` at `ce4daa4`.

- Added salted scrypt passwords and opaque, expiring server-side sessions with login, session restoration and logout.
- Added backend-enforced Administrator, Analyst and Viewer roles across protected application data and incident actions.
- Added development-only account provisioning with interactive/stdin passwords and no shipped account credentials.
- Added persistent login throttling, exact-origin validation, session-bound CSRF tokens and safe cookie configuration.
- Added authenticated web incident acknowledgement, investigation, assignment, resolution and reopening with required decision notes and optimistic revision checks.
- Added durable authenticated identity references and prior-assignment details to investigation audit history; retained historical system/CLI attribution.
- Added administrator account role/activation controls with session revocation and security events.
- Added migration 004 without replacing synthetic data, registry snapshots, alerts or existing audit events.
- Updated the React workspace with sign-in, session expiration handling, logout, analyst queues, role-aware controls and actionable errors.
- Changed Compose startup to seed only pristine synthetic data; explicit pipeline execution still replaces synthetic data by design.
- Added negative security tests, role-aware browser workflows, architecture diagrams, threat model, operations guidance and a five-minute demonstration.

No public deployment, repository visibility change or production compliance claim is included. Current test results and limitations are recorded in [VERIFICATION_4.0.md](VERIFICATION_4.0.md).

## Security review corrections

Corrections to reviewed commit `db17958bc16211853a4c042aae0df46640ef2f4b`, on existing PR #4:

- Added migration 005 for durable account revisions and indexed login-window expiry; prior migrations remain unchanged. Retained databases upgrade forward; only `carerank_test` permits the test-reset downgrade.
- Account updates check `expected_revision` inside the locked transaction. React sends only changed fields, reloads after 409, and resets local form state when the account revision changes. Stale forms cannot restore revoked roles or reactivate disabled accounts.
- Nginx and Vite overwrite a dedicated client-address header. The API accepts it only from explicitly trusted immediate proxies, keeps Uvicorn forwarding disabled, and applies separate account and source login budgets. Compose exposes only the web port.
- Blocked sources are rejected before username lookup/allocation. A serialized 10,000-bucket limit prevents further allocation at capacity; indexed expiry cleanup removes at most 100 rows per allocation attempt and never evicts live limits.
- Added a restricted database runtime-role provisioning command. Compose, CI and cloud startup keep API credentials separate from migration/operator credentials. Setup preserves existing passwords while generating any missing runtime secret.
- Added regressions for stale account changes, concurrent administrator revocation and last-administrator changes, failed-audit rollback, proxy spoofing, limiter growth/capacity/expiry, account CSRF/role boundaries and runtime database permissions.
- Corrected the cloud startup helper to require 401 for anonymous provider access without weakening authentication.

Executed evidence belongs in [VERIFICATION_4.0.md](VERIFICATION_4.0.md); test definitions and intended CI steps alone are not passing results. See [the correction review](SECURITY_REVIEW_4.0.md) for root causes and remaining deployment blockers.

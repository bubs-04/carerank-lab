# CareRank 4.0 security and threat model

CareRank 4.0 implements application authentication and analyst authorization for an isolated educational data operations workspace. These controls do not establish regulatory compliance or make the application suitable for patient data or clinical decisions. Current verification evidence is in [VERIFICATION_4.0.md](VERIFICATION_4.0.md).

## Assets, actors and trust boundaries

Protected assets include account password hashes, bearer sessions, registry snapshots and provenance, synthetic ranking data, incident state and attribution, and audit history. Public CMS records are public at their source; access to the workspace's combined history is still authenticated.

The browser, request headers and submitted actor/role values are untrusted. React is a convenience layer, not an authorization boundary. FastAPI validates every protected request. The database trusts the API's restricted runtime identity; migration and operator credentials have broader authority and must be held separately. Database administrators, host administrators and development CLI operators remain privileged actors.

| Role | Permitted web operations |
|---|---|
| Viewer | Read ranking, analytics, registry evidence, monitoring incidents and audit history |
| Analyst | Viewer operations plus incident notes, acknowledgement, investigation, assignment, resolution and reopening |
| Administrator | Analyst operations plus account role/activation management and security-event inspection |

External ingestion, monitoring backfill, migration, provisioning and synthetic dataset replacement remain operator CLI tasks. Possession of a web Administrator account does not grant a browser endpoint for these tasks. There is no public registration endpoint.

## Implemented controls

| Threat | Control | Residual boundary |
|---|---|---|
| Password disclosure | Per-password random salt; standard-library scrypt at N=32768, r=8, p=3; 12–256 character provisioning policy; constant-time hash comparison | No MFA, SSO, breached-password service, recovery or password rotation UI; choose unique development passwords |
| Session theft or fixation | Fresh 256-bit opaque session tokens; SHA-256 digest at rest; HttpOnly, SameSite=Strict, Secure-by-default cookie; absolute expiry (8 hours by default, configurable 60–86400 seconds); login replaces the presented prior session | Compromised browser/host or active XSS can act with a user's session; no device-bound sessions |
| Continued use after logout or account change | Logout deletes the session; inactive accounts fail authentication; role/activation changes revoke affected sessions; mutation transactions recheck identity/session and role | A completed request cannot be revoked retroactively |
| CSRF and login CSRF | Exact configured `Origin` check for login and mutations; reject cross-site Fetch Metadata; session-bound `X-CSRF-Token` required for authenticated writes; strict cookie SameSite | Origin configuration and trusted reverse-proxy behavior are deployment responsibilities |
| Forged administrator or analyst identity | Backend dependencies enforce roles; actor identity is loaded from the active session; action schema rejects extra fields | Database/host operators can bypass application authorization |
| Brute-force login and account enumeration | PostgreSQL-backed atomic windows across workers: 10 attempts per normalized username and 30 per peer address per 15 minutes; equal-cost verification for unknown users; generic credential error | Limits include successful logins; shared proxies/NATs share a bucket; distributed attacks and volumetric DoS require gateway controls |
| Overwritten investigation or stale privileges | Expected alert revision, transaction/advisory locks, current role/session recheck and atomic alert/event commit | Locks serialize short write operations; throughput at production scale is unverified |
| Audit tampering | Incident and security audit tables reject UPDATE/DELETE with database triggers; runtime grants allow SELECT/INSERT only; actor IDs, prior/new state, assignment and decisions retained | Schema owners can disable triggers or alter schema; off-host tamper-evident retention is not implemented |
| Injection and sensitive error output | ORM-bound queries, bounded typed request fields, allowed lifecycle states/roles, sanitized database and validation errors; no password or raw session in audit | Decision notes are operational content and visible to all workspace readers; operators must not enter secrets or patient information |
| Browser data leakage | API `Cache-Control: no-store`, nosniff, frame denial, no-referrer, restricted Permissions-Policy; Nginx self-origin Content Security Policy; React escapes text | No independent penetration/accessibility audit; Vite is a development server, not a production boundary |
| Destructive startup | Bootstrap checks providers, encounters, scores and pipeline history and seeds only when all are empty; startup lock is distinct from the pipeline transaction lock | Explicit pipeline/benchmark tools still replace synthetic data; do not run them on retained data |

Unauthenticated `/api/health` returns service health only. OpenAPI/docs are public contract metadata. All ranking, analytics, registry and monitoring data endpoints require authentication. Login error handling excludes rejected credential values from validation responses. API bodies, passwords, raw tokens and decision notes are not logged by application security events.

The API container runs as a non-root user. The default Uvicorn command uses `--no-proxy-headers`: arbitrary `X-Forwarded-For` values do not select a new login-rate bucket. With Nginx/Vite, peers can share the proxy address. If a future deployment enables forwarded addresses, trust only the actual proxy network and have the proxy replace incoming forwarded headers; never trust all clients.

## Configuration and account lifecycle

No accounts or default passwords ship with the application. `python -m app.auth create-user` requires `APP_ENV=development`; use the interactive prompt or `--password-stdin`. Never pass passwords as command arguments or store them in source, screenshots, test logs, PR text or browser storage. The CLI fails on an existing username rather than silently resetting credentials.

`AUTH_COOKIE_SECURE=true` is the default. Setting it false is rejected outside explicit development mode. For local HTTP only, use `APP_ENV=development`, `AUTH_COOKIE_SECURE=false`, and an exact `AUTH_ALLOWED_ORIGINS` value such as `http://127.0.0.1:5173`. Different hostnames or ports are different origins. Shared deployments require HTTPS and an explicitly configured HTTPS origin. Secure cookies alone do not configure TLS.

Administrators can change roles or deactivate accounts through the Administration workspace and protected account API. The last active administrator cannot be demoted/deactivated. These changes append a security event and invalidate the affected account's sessions. Deactivation preserves assignment and audit identity references; it does not erase history. Historical CLI actions retain self-reported labels and no authenticated actor ID. The UI distinguishes those labels from authenticated accounts.

## Restricted database runtime

The supplied Compose stack is an isolated local development topology. Its PostgreSQL owner account is shared by migration/CLI/API for convenience; that is not a least-privilege production configuration. Use separate credentials before any shared deployment:

1. Run migrations as the schema owner, never as the API runtime role.
2. Create a new login role with a unique secret using a PostgreSQL administrator and an interactive password prompt, for example `createuser --login --pwprompt --no-superuser --no-createdb --no-createrole carerank_api`. Do not make it an owner or member of a privileged role.
3. Apply [runtime-grants.sql](runtime-grants.sql) as the owner/administrator to the intended database: `psql -v ON_ERROR_STOP=1 -v runtime_role=carerank_api -d carerank -f docs/runtime-grants.sql`. The script refuses an absent, privileged, owning or inherited role, removes its broad grants, and restricts schema creation.
4. Supply this role's connection URL only to the API. Keep migration, provisioning, ingestion and pipeline operator credentials separate. The runtime role cannot perform those operator operations.
5. Recheck grants after schema changes and verify denial of registry/pipeline DML, schema creation and audit mutation. Keep database ports private, backups encrypted, and secrets in the deployment's secret manager.

The script permits SELECT on existing domain tables, UPDATE on alert state and account role/activation, SELECT/INSERT on append-only audit tables, and session/rate-limit maintenance. It grants no table ownership, DDL, synthetic/registry writes, audit UPDATE/DELETE, account creation or monitoring evaluation. `SELECT ... FOR UPDATE` requires UPDATE permission in PostgreSQL; session and account mutation paths have corresponding narrowly scoped grants. PostgreSQL role membership can reintroduce privileges, so do not add inherited roles afterward without review.

## Operational limits and deployment gate

This release has no multi-tenant isolation, enterprise identity provider integration, MFA, production account recovery, external audit sink, security alert delivery, scheduled ingestion, session-device management or production load certification. Audit history and login windows grow with use; expired sessions/windows are cleaned during login, while audit retention requires an explicit policy. Notes and usernames remain potentially sensitive operational data even though no patient records are ingested.

Before a shared deployment, design identity provisioning/recovery, terminate TLS at a managed trusted proxy, restrict database credentials, configure backup/restore and retention, monitor login failures/lock waits, test rate-limit capacity, and obtain independent security review. These are documented unverified requirements, not claims that the present development deployment satisfies them. No public deployment or cloud expenditure is part of this delivery.

## Verification scope

Negative tests should exercise unauthenticated reads, every role boundary, CSRF/origin failures, expired/revoked sessions, inactive accounts, stale revisions, invalid assignments and forged identity fields. PostgreSQL tests additionally cover concurrency, audit immutability, migration preservation and restricted runtime permissions. Browser tests use `carerank_test` for lifecycle writes; destructive tests must never use `carerank`. Actual executed results, failures/fixes and remaining gaps are recorded separately in [VERIFICATION_4.0.md](VERIFICATION_4.0.md).

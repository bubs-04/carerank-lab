# CareRank 4.0 integration and release assessment

Implemented in the isolated published cloud development workspace from fetched `main` commit `ce4daa4bbcc56324a9db76133075639c424f9a12` (merged PR #3). Feature branch: `feat/enterprise-security-operations`. This report supersedes earlier release reports only for 4.0; previous evidence remains historical.

## Implemented scope

- Local password authentication using salted scrypt; opaque server sessions stored as token hashes; Secure-by-default, HttpOnly, SameSite=Strict cookies; absolute expiration, rotation and logout.
- Backend authorization for Administrator, Analyst and Viewer. All ranking, analytics, registry and monitoring data requires authentication. Health and API contract documentation remain public.
- Exact-origin checks, session-bound CSRF validation, persistent login throttling, sanitized validation/database failures, no-store API responses and browser security headers.
- Authenticated incident acknowledgement, investigation, assignment, resolution, reopening and notes. Revision conflicts return 409; authorization is checked again inside the locked write transaction. An alert update and its attributed audit event commit together.
- Administrator UI/API for account role/activation changes and security history. Changes revoke affected sessions; the last active administrator is protected.
- Development-only provisioning CLI with prompted/stdin passwords and no shipped accounts. Migration 004 adds four authentication tables and nullable actor/assignment references, retaining historical CLI/system attribution.
- Accessible sign-in, analyst queues, status/severity/assignment filters, editable investigations, timelines, administration, expiration recovery and conflict/error handling. Existing ranking, registry comparison, mobile navigation and Refresh status remain covered.
- Safe pristine-only Compose bootstrap, disabled proxy-header trust by default, a validated least-privilege PostgreSQL grant script, updated CI, diagrams, threat model, README, changelog and five-minute demo.

## PostgreSQL and preservation

The main cloud development database is `carerank` on local PostgreSQL 16. Schema reset, downgrade, fault-injection, lifecycle mutations and browser investigation workflows ran only on `carerank_test`. Test fixtures explicitly reject other database names. Neither the Mac database nor a remote production database was used.

Migration **003 → 004** preserved row counts and hashes of all original columns in all **14 existing data tables**. Counts remained: 1,000 providers; 100,000 encounters; 1,000 scores; one pipeline run; one registry source; two snapshots; two registry runs; ten records; one snapshot change; eight findings; twelve monitoring rules; 24 evaluations; eight alerts; eight audit events. Historical alert states and event contents were unchanged, not merely their counts. Main now reports revision 004. New development accounts and authentication events are additive.

The test API used a separate `carerank_api_test` login with the shipped runtime grants. PostgreSQL rejected registry/synthetic deletion, audit UPDATE/DELETE, schema creation and password-hash changes with insufficient-privilege errors. Real login, session maintenance, analyst writes and administrator actions ran successfully with this restricted role. The retained main development stack still uses its original owner binding; production separation is documented rather than silently changing persistent environment assets.

## Executed verification

Logs and screenshots are under `verification/v4.0/`.

| Check | Result | Evidence |
|---|---|---|
| Backend unit and PostgreSQL integration/security suite | **156 passed, 1 skipped** | backend.txt |
| React tests with real login → proxy → API → PostgreSQL enabled | **46 passed, no skips** | frontend-live.txt |
| TypeScript and production build | Passed | build.txt |
| Ruff lint and Python format | Passed, 51 files formatted | backend-lint.txt, backend-format.txt |
| Frontend formatting | Passed | frontend-format.txt |
| Playwright with configured Chromium and restricted PostgreSQL runtime | **10 passed, no skips** | playwright.txt |
| Existing launcher regression tests | **3 passed** | launcher.txt |
| PostgreSQL runtime permission denials | Passed | database-permissions.txt |
| Main data content/count preservation and authenticated reads | Passed | main-preservation.txt, before-content.json |

Backend negative tests cover anonymous/forged identities, Viewer mutation denial, Analyst administration denial, invalid/missing CSRF and foreign origins, expired and revoked sessions, inactive accounts, secure-cookie configuration, session rotation, generic login failures and rate limiting across clients. Additional tests inject revocation, deactivation and demotion between authentication and the locked incident write to prove authorization is rechecked. Concurrent decisions have one winner, with one matching audit revision. Migration preservation, append-only triggers, evaluation rollback/deduplication and the 1.0–3.1 regression suites executed against PostgreSQL.

Browser tests use configured `CHROMIUM_PATH` and real same-origin cookies. They cover legacy ranking/search/pagination/profile/comparison/analytics and registry workflows, mobile and Refresh status, unauthenticated protection, Viewer restrictions, CSRF/origin checks, logout replay denial, administration and the complete assigned incident lifecycle with authenticated audit assertions. See playwright.txt for the final run.

## Failures found and corrected

- Initial bootstrap review found a deadlock from reusing the pipeline's advisory lock on another connection. Bootstrap now uses a distinct lock; the PostgreSQL test executes pristine initialization and confirms repeat startup preserves data/history.
- A stale aborted API response could dispatch session expiration after newer data arrived. The hook now ignores an aborted response's 401, with a regression test retaining the current result/session.
- The first dedicated test API port was already occupied. Its login failures were diagnosed as a test routing error; the isolated test API moved to port 8014 and its authenticated account ID was checked against `carerank_test` before rerunning.
- The live React check's one-second initial wait was too short for session restoration followed by the analytics request. It now retains the same content assertion with a bounded ten-second wait; the focused and full authenticated suites passed.
- New browser locators matched a select's wrapping label and a decision note in both the editor and existing history. Tests now target the exact accessible combobox and the audit list, with a unique note per run, retaining lifecycle and audit assertions.
- Screenshot review found the mobile session bar inherited a fixed generic header height and overlapped navigation. Its height now follows its contents. The browser workflow checks that Sign out fits inside the account banner at 390px width.

No failing assertion was disabled, no authorization guard was removed for a test, and no destructive test targeted main data. Component-only existing domain tests use explicit read identities; separate security tests use real passwords, cookies and PostgreSQL with no identity override.

## Operational notes and limits

The persistent `/workspace/.carerank` installation/session scripts were not modified. Native API processes were restarted with explicit development settings and proxy headers disabled. The older startup script's final anonymous provider probe now receives the intended 401; use health plus an authenticated read for readiness. Development passwords are in the owner-readable cloud file `/workspace/.carerank/accounts-4.0.json`, outside Git. No credentials, raw session cookies, traces, database files, dependency directories or built assets are included in this delivery.

The optional live CMS network test was not run. Existing nonfatal Starlette/httpx and lucide-react bundler warnings remain. Dependencies were reused, not freshly installed. Remote CI, fresh Docker image builds, production load, TLS deployment, backup restoration, independent penetration testing and formal accessibility/compliance certification are not established by local checks. Local accounts have no SSO/MFA, production recovery/rotation workflow, multi-tenant isolation or external tamper-evident audit sink. Shared deployment requires the identity, TLS, least-privilege, retention and operational controls described in [SECURITY_4.0.md](SECURITY_4.0.md).

**Assessment:** suitable for review as a working, verified cloud-development release. Shared production deployment remains gated by the documented operational and identity requirements. No merge, public deployment, repository visibility change or new cloud service was performed.

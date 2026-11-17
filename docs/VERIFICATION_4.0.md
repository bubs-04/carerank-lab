# CareRank 4.0 security correction verification

These corrections update existing draft [PR #4](https://github.com/bubs-04/carerank-lab/pull/4) on `feat/enterprise-security-operations`, from independently reviewed commit `db17958bc16211853a4c042aae0df46640ef2f4b`. The original 4.0 implementation remains intact; [the previous report](verification/v4.0-review/PREVIOUS_REPORT.md) and `verification/v4.0/` are historical evidence. This report supersedes their runtime-credential, readiness and proxy descriptions.

## Implemented corrections

1. **Stale administrator updates:** additive migration 005 introduces durable account revisions. Account PATCH requires the reviewed revision, checks it while holding the security/row locks, returns 409 on conflict, increments it on success, and commits account changes, session revocation and prior/new-state audit together. React sends only changed fields, reloads on typed 409 errors, resets cached controls by account revision, and requires a deliberate retry. Last-administrator and acting-identity rechecks remain enforced.
2. **Proxy-wide throttling:** Nginx and Vite overwrite the dedicated client-address header and remove caller-supplied forwarding alternatives. The API trusts only configured immediate proxy addresses, normalizes IPv4-mapped addresses, rejects malformed/scoped/chained trusted headers, and otherwise uses the socket peer. Compose publishes only localhost web access through a frontend network, with a separate internal API proxy network and reserved Nginx address outside the dynamic allocation range. Uvicorn proxy rewriting remains disabled.
3. **Unbounded throttle state:** an exhausted source returns before username lookup/allocation, counts or cleanup. PostgreSQL serializes source/account budgets and the 10,000-bucket allocation ceiling. Expiry cleanup uses the new `(window_start, key)` index and deletes at most 100 expired rows; live limits are not evicted. Existing over-cap legacy tables stop growing and drain through bounded expiry cleanup.
4. **Database authority:** Compose, CI and the cloud API use distinct restricted runtime credentials. `app.runtime_role` rejects unsafe roles or mismatched database targets and applies explicit grants. Operator migrations, ingestion and account provisioning retain separate credentials. Setup preserves existing secrets. The cloud helper now expects anonymous provider requests to return 401 and removes owner/test credential variables when launching API/Vite processes.

[Security-review mapping](SECURITY_REVIEW_4.0.md) describes root causes, exact controls, regressions and residual risks. [File inventory](FILE_CHANGES_4.0.md) lists source changes; [architecture](ARCHITECTURE_4.0.md), [threat model](SECURITY_4.0.md), README and changelog are updated.

## PostgreSQL preservation

On the retained cloud PostgreSQL 16 `carerank` database, **004 → 005 preserved row counts and SHA-256 hashes across every pre-existing column in all 18 existing tables**. Existing synthetic data, registry snapshots/records, alerts, monitoring audits, accounts, sessions, throttle rows and security audits were unchanged. Existing accounts received revision 1; the expiry index was added. Evidence: `verification/v4.0-review/main-before-005.json` and `preservation.txt`.

Migration 005 refuses downgrade for retained databases. Only the reserved disposable `carerank_test` PostgreSQL database or temporary SQLite unit-test database of that name can be reset. Migrations 001–004 were not rewritten. PostgreSQL security fixtures also exercise 003→004 and 004→005 preservation.

All destructive PostgreSQL tests, concurrency/fault injection and browser lifecycle writes used `carerank_test`. The Compose browser stack used its own local PostgreSQL container and restricted `carerank_api_test` role. The published cloud main database and its data were retained; no Mac or external database was accessed.

## Executed evidence

Evidence is under [`verification/v4.0-review/`](verification/v4.0-review/). Results below are actual local cloud executions. The latest commit-specific remote run is linked in PR #4's Checks and delivery description; historical CI on the reviewed commit is not evidence for these corrections.

| Check | Result | Evidence |
|---|---|---|
| Complete backend unit/PostgreSQL suite | 191 passed, 1 optional live CMS test skipped | backend-final.txt |
| Additional retained-database downgrade guards | 2 passed | migration-guard.txt |
| React with authenticated proxy/API/PostgreSQL workflow | 51 passed; no skips | frontend-live.txt |
| TypeScript and production build | Passed | build.txt |
| Ruff lint / format | Passed; 55 files | backend-lint.txt, backend-format.txt |
| Frontend formatting | Passed | frontend-format.txt |
| Launcher/configuration regressions (mocked; no Mac database) | 4 passed | launcher.txt |
| Actual Nginx: separate clients and spoofed forwarding | Passed | proxy.txt |
| Chromium Playwright workflows | 10 passed; no skips | playwright.txt |
| Main 004→005 content/count preservation | All 18 tables preserved | preservation.txt |

The backend run includes real PostgreSQL tests for interleaved stale role/reactivation writes; revoking an administrator during an in-flight request; concurrent last-administrator changes; audit-INSERT failure rolling back account changes and session deletion; unauthorized/CSRF-invalid account writes; concurrent bucket allocation and source limits; bounded expiry cleanup; and restricted-role permission denials. Existing ranking, ingestion, snapshot comparison, monitoring evaluation/deduplication/lifecycle, sessions, logout and role tests remain enabled.

## Failures diagnosed and corrected

- Component tests exposed a second stale-form issue: React could retain local controls across a batched refresh. Including the durable revision in the form key resets them to the newly loaded account state.
- An audit-failure regression initially expected an exception, but the existing API correctly returned its sanitized database 503. The test now asserts that response and verifies actual database/session/audit rollback; it does not bypass the handler.
- The new downgrade guard rejected two older SQLite roundtrip fixtures named `migration.sqlite`. The fixtures now use reserved disposable `carerank_test`; their original preservation and immutability assertions remain unchanged. Both affected tests passed before the full-suite rerun.
- The cloud Docker build initially lacked the session proxy CA. Temporary Dockerfile copies mounted the existing CA bundle as a BuildKit secret for pip/npm, keeping TLS verification enabled and the CA out of image layers. Repository Dockerfiles do not embed cloud-specific certificates.
- The unprivileged Nginx image could not read a source configuration with owner-only checkout permissions. Its Dockerfile now explicitly copies that public configuration with mode 0644.
- A proxy-only internal Docker network did not expose the web port. A separate frontend network now supplies localhost ingress while the API remains private. The dynamic proxy allocation range excludes Nginx's fixed trusted address, preventing collisions during replacement/one-off clients. Early live/proxy checks failed on connection/DNS readiness; final results are recorded above after these fixes.

No tests were disabled, security assertions weakened, authorization bypassed or main-database data reset.

## Remaining limits and review gate

The optional live CMS network test remains unexecuted. Nonfatal Starlette/httpx deprecation and lucide-react bundle warnings remain. Shared/public deployment is blocked on deployment-specific secret delivery/rotation, verified TLS/proxy topology, production account provisioning/recovery (or SSO/MFA), backup/restore and retention, load/abuse monitoring, and fresh independent security review. Global limiter capacity is deliberately fail-closed; distributed exhaustion, NAT sharing and security-lock contention remain availability risks. There is no multi-tenant boundary, external tamper-evident audit sink or compliance certification.

**Assessment:** the corrections passed local development verification and are ready for fresh independent review of the updated PR head. Local development verification is not public-production approval. PR #4 remains a draft; no merge, public deployment, visibility change or new paid cloud service is authorized or performed.

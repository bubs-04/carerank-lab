# CareRank 6.0 security and demo remediation

Reviewed baseline: `a9aea181b02f6dd4778655f78021a4ee728e789f`. Tested application checkpoint: `b2098ce66b666a6d192d3181fd01b4e117fba488`. Existing draft PR [#6](https://github.com/bubs-04/carerank-lab/pull/6) is retained. A documentation-only follow-up records this evidence; it changes no tested application code.

## Findings and corrections

| Finding | Correction and exact implementation files |
|---|---|
| **P0: URL does not establish PostgreSQL identity** | `backend/app/database_safety.py` rejects connection-routing query/env overrides, then checks server `current_database()`, `current_user` and `session_user`. `backend/tests/test_observability.py` verifies before migrations and again before truncation on the same transaction. `backend/migrations/env.py` supports the supplied verified connection and validates all PostgreSQL migration connections; `backend/migrations/versions/007_reliability.py` checks the bound disposable target before downgrade DDL. `backend/app/demo.py` checks every preparation transaction, including connections opened by seeding/ingestion. SQLite downgrade also checks its actual attached file. |
| **P0: demo reset could select a remote daemon** | `scripts/demo.py` inspects the selected context, including custom `DOCKER_CONFIG`; rejects `DOCKER_HOST`, TCP/SSH/unknown socket endpoints; verifies an approved local Unix socket and ownership. All daemon/Compose/volume operations use that explicit endpoint. Docker Desktop, local rootless Docker and the managed cloud socket are supported. Exact project/volume labels and explicit reset confirmation remain required. |
| Missing demo accounts silently generated unusable replacements | `scripts/demo.py` refuses startup if a retained volume lacks either original private configuration or accounts. It directs the operator to restore matching files and generates no replacement credentials. Daemon lookup errors cannot be mistaken for an absent volume. |
| Failed archive checksum suppressed retry | `backend/app/demo.py` requires a succeeded/no-change run joined to an existing published snapshot. Failed/incomplete attempts remain intact; a later attempt can safely publish or reuse the snapshot. The loaded flag reflects verified publication. |
| Archive replay presented as fresh CMS retrieval | `backend/app/monitoring/api.py`, `backend/app/monitoring/schemas.py`, `frontend/src/Monitoring.tsx` expose/display ingestion kind, original capture time and replay-start time from each run, including no-change runs sharing snapshots. Fresh CMS, offline replay and artificial fixtures remain distinct. |
| Worker could pulse healthy before a failed tick | `backend/app/operations/worker.py` publishes idle only after recovery, reconciliation, scheduling and claim checks succeed. Tick/lease-renewal failures mark presence degraded; unavailable PostgreSQL leaves presence to expire. Existing publication fencing is retained. |
| Unexpected 500 lost correlation / Uvicorn leaked errors | `backend/app/main.py`, `backend/app/observability.py` persist the validated/generated request ID for the outer 500 handler, return a generic error with that header, and route Uvicorn error logs through the sanitized formatter. |
| Oldest queued work implied immediate claimability | `frontend/src/Reliability.tsx` now labels the SQL result as **due queued or retry work**, explicitly including blocked work that may not yet be claimable. SQL semantics are unchanged. |
| Deployment receipt, cleanup and startup polling defects | `infra/deploy.py` treats the local receipt as unverified consistency metadata, not a GitHub approval gate. It records the separate operator change reference. Cleanup holds a validated secret-directory descriptor and covers early manifest/approval/receipt/config/pull failures as well as later failures. Worker readiness retries transient failures/timeouts within bounded attempts. |

Documentation changes: `docs/DEMO_6.0.md`, `infra/README.md`, this report, the pointer in `docs/RELEASE_6.0.md`, and `docs/verification/v6.0-remediation/results.json`. No migration schema change, dependency replacement, authentication weakening or additional feature was introduced.

## Regression tests and preservation

Exact regression-test files:

- New `backend/tests/test_database_safety.py`: URL/libpq overrides fail before connection; real mismatched connections use a fresh disposable `carerank_guard_<random>` database; migrations/truncation/seeding are refused with its sentinel and schema intact; connected-user and subsequent-transaction checks are covered. No mismatch experiment points at retained main/demo data.
- Updated `backend/tests/test_demo_archive.py`: failed publication with retained checksum, incomplete success/no-change/running records, safe retry and idempotent published-snapshot reuse.
- New `backend/tests/test_worker_readiness.py` and `backend/tests/test_http_error_privacy.py`: failed ticks after prior healthy presence, recovery, lease failures, and real Uvicorn H11 error handling. Harmless synthetic exception/query/header markers cannot leak through responses or approved logs.
- Updated `backend/tests/test_monitoring.py`, `frontend/src/Monitoring.test.tsx`, `frontend/src/Reliability.test.tsx`: mixed fresh/replay/fixture histories and shared snapshots; capture/replay timestamps; accurate blocked-work wording.
- Updated `scripts/tests/test_release_safety.py`: remote contexts/hosts, custom Docker config, Desktop socket paths, labels/confirmation, missing account files, failed daemon lookup, advisory receipts, cleanup at early/late failure phases, directory substitution, transient readiness and bounded exhaustion. Docker, deployment and remote operations are mocked; no remote volume is deleted.

This adds **37 backend cases, 1 frontend case and 45 script cases** over the reviewed baseline, with existing assertions retained or updated to the corrected semantics. A test fixture initially returned incomplete mocked `stat` data and broke pytest capture; the mock was corrected to preserve real stat fields. This was a harness defect, not a relaxed assertion.

Retained-data verification: captured sorted-row SHA-256 hashes/counts, updated and restarted the existing demo **without reset**, then rechecked after native cloud restart. All **23 main and 23 demo tables** matched exactly, including schema-version rows, provider scores, registry history, accounts, investigations and pipeline/audit evidence. Only transient `pipeline_workers` presence was excluded. Private account/configuration files were retained. Migration remains 007. Destructive schema tests used disposable databases only; no Mac database was accessed.

## Complete verification

Local and independent [GitHub CI run 44507118297](https://github.com/bubs-04/carerank-lab/actions/runs/44507118297) passed on `b2098ce`:

| Check | Result |
|---|---|
| Backend unit, PostgreSQL integration and security | **270 passed, 1 optional live-CMS skipped** |
| React including live PostgreSQL API workflow | **66 passed** |
| Launcher/deployment/safety scripts | **60 passed** |
| Playwright including security, analyst lifecycle, scheduling/recovery, mobile and previous workflows | **12 passed** |
| TypeScript, production build, lint and formatting | Passed |
| CloudFormation static validation; container builds | Passed, no AWS provisioning |
| CI reverse-proxy source isolation and spoofing | Passed |

Focused tests preceded the pushed checkpoint; the full local regression and independent CI then ran once each. Existing screenshots were not regenerated into the source change. No assertions were weakened, no tests disabled, and no data reset was performed on retained databases.

## Remaining gates

**A short independent re-review of both P0 fixes is requested before merge.** Review actual connection identity and transaction placement, and local socket/context selection through every reset operation. PR #6 remains draft; passing tests are not independent security approval.

The deployment helper does not authenticate a locally supplied receipt or human approval reference. A trusted root operator must independently verify the protected GitHub workflow and approved change. Missing/ambiguous manifest secret locations, symlink directories or inaccessible paths fail closed without authorizing deletion of unknown files; operator cleanup is required when no safe location can be established. Actual Docker Desktop socket behavior is covered by mocks, while the managed local socket was exercised. AWS deployment, production identity lifecycle/SSO/MFA, cloud failover and cryptographically verified release provenance remain unverified. The prior real CMS archive network blocker remains; mixed-history tests use explicitly artificial fixtures, not a claimed live CMS capture.

No merge, competing PR, visibility change, public deployment or paid cloud provisioning occurred.

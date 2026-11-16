# CareRank 3.0 verification report

Date: 15 November 2026. Environment: isolated task workspace on macOS. No existing user database, running Docker services, global dependencies or GitHub state were changed.

## Baseline and access

Implementation extends the complete delivered CareRank Lab 2.0 source ZIP (106 files). The newer attachment `CareRank_Lab_2.0_Project (7).zip` was also compared: all 106 files are byte-identical to that baseline. GitHub `ls-remote` failed because private authentication was unavailable. No current remote commit/branch equality is claimed. An isolated local baseline commit and `feat/cms-data-ingestion` branch were used solely to generate a reviewable patch. The patch must pass `git apply --check` in the actual repository; otherwise supply the current branch ZIP for reconciliation.

## Executed checks

| Check | Actual result | Boundary |
|---|---|---|
| Backend pytest suite | **67 passed, 17 skipped** | 39 new portable ingestion checks plus existing scoring/analytics checks; executed with in-memory/disposable SQLite |
| PostgreSQL integration | **16 skipped** | Includes 2 new registry publication/concurrency tests; no disposable PostgreSQL access |
| Optional live pytest test | **1 skipped by default** | Live CLI was exercised separately; no claim this opt-in test ran |
| Frontend Vitest | **20 passed, 1 skipped** | 7 new DataOps checks; existing stale-response and analytics tests retained |
| Optional live DOM workflow | **1 skipped** | No upgraded full application server available |
| TypeScript/Vite production build | **Passed** | Existing lucide use-client bundler warnings remain |
| Ruff check/format | **Passed** | 29 Python files checked/formatted |
| Prettier | **Passed** | New and existing frontend source, config and E2E files |
| Existing launcher unit tests | **3 passed** | Stubbed Docker behavior only |
| Alembic round trip | **Passed on SQLite** | 001 → 002 → 001 → 002 preserved a synthetic sentinel provider; not PostgreSQL DDL verification |
| Compose config | **Passed** | Parsed using a transient nonsecret validation password; no local .env created/replaced |
| Docker engine | **Blocked** | Socket permission denied; no container startup or migration attempted afterward |
| Playwright | **1 failed, 2 did not run** | Chrome aborted before navigation (SIGABRT; cleanup EPERM). Stopped after first launch failure |
| Browser/screenshots | **Not verified / none captured** | No screenshots or mockups represented as actual application evidence |
| Word guide | **Structural validation** | DOCX ZIP/XML/tables and diagram inspected; Word pagination not rendered |
| Remote CI | **Not run** | Workflow updated locally; no push, PR, merge or publication |

The initial host lacked optional SOCKS support needed by its network proxy. `socksio==1.0.0` was installed only into an isolated task dependency directory, activated only for live verification. No global Mac environment or application dependency pin changed. The connector now reports that missing optional dependency with a safe error code. TLS verification and proxy controls remained enabled.

## Actual live CMS evidence

The finalized CLI fetched CMS metadata, streamed a 1,000-row prefix from the official CSV URL, rechecked metadata and persisted the result in an **isolated SQLite database**, not PostgreSQL and not the existing Mac database.

- Dataset: `mj5m-pzi6`.
- Source release reported by metadata: `2026-11-12`; modified: `2026-10-30`.
- Captured rows: **1,000**; accepted: **1,000**; rejected: **0**; warning findings: **0**.
- Distinct NPIs: **421**, confirming that row count is not clinician count.
- Second finalized live retrieval: **no_change / Version reused**; same snapshot ID and exactly **one** CMS snapshot retained.
- Exact run IDs, retrieval/capture timestamps, selected-content checksum, scope and source provenance: `verification/v3/live-result.json`.
- CLI output: `live-final-first.txt` and `live-final-rerun.txt` in the same directory.

This verifies real network retrieval and the complete CLI ingestion path on SQLite. It does not certify PostgreSQL isolation/locks or browser behavior. Recorded job durations are operational observations, not a benchmark or scalability claim. The complete national file was not downloaded or checksummed. Live source records and the task database are not bundled in the source ZIP; only summary evidence and artificial fixtures are included.

## Deterministic fixture evidence

CLI fixture A, fixture B, and B again executed successfully. Each capture has 5 rows: 4 valid, 1 rejected, 3 optional-value warning findings. The comparison produced 1 added, 1 removed, 1 changed and 2 unchanged accepted records; one retained identity changes specialty and city. Repeating B reused its version. See `fixture-cli.txt` and the summary in `live-result.json`.

Portable tests additionally cover invalid/missing identifiers, optional blanks, duplicate identities, unexpected schema, malformed/truncated downloads, byte/deadline bounds, source-release changes, HTTP retry/permanent failures, interrupted streams, KeyboardInterrupt, all-invalid failure, failure immediately before commit, finding conservation, incompatible comparisons, reverted version reuse, row-order/finding alignment, read-only APIs and pagination. Foreign keys are enabled in SQLite transaction tests.

The PostgreSQL-only tests exercise advisory-lock-backed concurrent publication and idempotent publication while preserving synthetic provider counts. They are authored but skipped, not passing by assumption. The browser workflow is opt-in with DATAOPS_E2E=1 and requires the two fixture CLI runs; default CI runs those fixtures without CMS network access.

## Security and publication review

- Fixed CMS dataset/metadata endpoint; only HTTPS official-host CSV paths allowed; redirects disabled. No arbitrary URL ingestion API.
- Selected seven registry fields only. Names, phones, street lines, unused columns and response bodies are not persisted in normal records/logs.
- Safe error codes and structured application audit logs. No credential output in the ingestion CLI. Existing read APIs retain sanitized database errors.
- Registry tables and APIs have no relationship to fictional scores. Real/fixture modes use separate source IDs and explicit UI labels.
- Source ZIP excludes .env, .git, dependency directories, virtual environments, caches, build output, browser traces, backups and local databases. A heuristic secret scan is a limited check, not a guarantee for later personal edits.
- The existing application has no authentication. Localhost bindings are preserved. Public production deployment would require an authentication/authorization and operational review even though DataOps routes are read-only.

## Remaining work before calling the release verified locally

1. Reconcile with the private branch using patch check or a current branch ZIP.
2. Back up the real database and execute migration 002 in PostgreSQL following `UPGRADE_3.0_MAC.md`.
3. Run the full suite with TEST_DATABASE_URL pointing to a separate disposable PostgreSQL database.
4. Run fixture and bounded live CLI jobs in Docker; inspect source provenance/findings.
5. Run Playwright on the upgraded application and inspect desktop/mobile DataOps plus existing pages. Capture actual screenshots locally.
6. Open the Word guide in Word/Pages and inspect pagination before sharing it.

Known design limits: bounded-prefix sampling is not representative; membership deltas are not national clinician exits. NPI assignment/check digits and postal-city validity are not verified. No immutable raw-file archive, scheduler, heartbeat, retention policy, authentication, clinical governance, or large-scale performance guarantee is implemented. Failed database access may prevent final audit updates; hard kills can leave running audits for explicit operator recovery.

## Local Mac verification after integration

The results above describe the original isolated Work environment.
The following additional checks were completed on the existing Mac installation:

- PostgreSQL migration 001 -> 002 succeeded.
- Existing synthetic records were preserved: 1,000 providers, 100,000 encounters, 1,000 scores.
- PostgreSQL integration suite: 83 passed, 1 skipped, 2 warnings, using the separate carerank_test_v3 database.
- Fixture A and B ingestion succeeded against PostgreSQL.
- Fixture comparison produced 1 added, 1 removed, 1 changed, and 2 unchanged records.
- Repeating Fixture B reused its existing snapshot.
- Live CMS ingestion succeeded: 1,000 received, 1,000 valid, 0 rejected.
- Data Operations dashboard was manually verified.
- Refresh status navigation bug was corrected.
- Mobile navigation overflow was corrected.
- Playwright browser suite: 4 passed, including the refresh regression test.
- Frontend Vitest suite: 20 passed, 1 skipped.
- Frontend production build and Prettier formatting checks passed.

These results establish successful local verification, not production readiness.
GitHub Actions verification for the CareRank 3.0 branch remains pending.

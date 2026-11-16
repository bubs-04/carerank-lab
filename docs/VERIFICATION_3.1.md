# CareRank 3.1 verification report

> This is Work's original delivery report. Subsequent real PostgreSQL and Chromium verification is recorded in [CLOUD_INTEGRATION_3.1.md](CLOUD_INTEGRATION_3.1.md), including resolved environment blockers and fresh logs.

Prepared 16 November 2026. Source baseline: Git archive comment `351d7143b49b3f2e151d6877d0074ef050d53a60`. Development copy: `feat/data-quality-monitoring`. No push, merge, deployment, repository visibility change, user `.env` edit or user database mutation was performed.

## Executed results

| Check | Actual result | Evidence / practical limit |
|---|---|---|
| Backend pytest suite | **107 passed, 20 skipped** | verification/v3.1/backend.txt; 40 new portable monitoring tests plus 67 existing tests |
| PostgreSQL-specific tests | **19 skipped** | TEST_DATABASE_URL unavailable; includes 3 new PostgreSQL concurrency/audit/migration/rollback cases |
| Optional live CMS test | **1 skipped** | No live CMS retrieval performed for 3.1; CI does not require it |
| React/Vitest suite | **29 passed, 1 skipped** | frontend.txt; nine new monitoring tests; optional live full-stack DOM test skipped |
| TypeScript + Vite production build | **Passed** | build.txt; existing lucide-react use-client bundler warnings remain nonfatal |
| Python lint and formatting | **Passed** | ruff.txt; 39 Python files checked/formatted |
| Frontend formatting | **Passed** | format.txt |
| Compose configuration parse | **Passed** | compose-config.txt; example environment only, no engine/stack startup |
| Mac launcher tests | **3 passed** | launcher.txt; launcher itself not used to start/reseed the application |
| Deterministic fixture CLI | **Passed with isolated SQLite** | fixture-cli.txt: A, B, B produced 3 attempts, 2 snapshots, 36 evaluations and 12 alerts; backfill found no missing profiles; investigation appended revision 2 |
| SQLite migration 002 → 003 → 002 → 003 | **Passed in tests** | Existing registry records and a synthetic sentinel preserved; append-only event triggers rejected UPDATE/DELETE |
| SQLite concurrent evaluation/triage | **Passed in tests** | One evaluation profile, deduplicated alerts and one successful state decision per expected revision; not a PostgreSQL concurrency claim |
| Local HTTP smoke | **6 passed with verification-only SQLite session adapter** | running-http-adapter.json; real Uvicorn/Vite HTTP, with the request session dependency adapted for SQLite; not the production PostgreSQL stack |
| Baseline preservation | **17 core files byte-identical** | preservation.json: scoring, generator, pipeline, analytics, CMS connector/validation/comparison, migrations 001/002, App mobile navigation, useApi race protection and dependency manifests |
| Source archive / review patch | **Checked during packaging** | delivery-check.json: patch application and complete file-byte comparison against the exact uploaded baseline |
| Word guide structure | **Checked during generation** | DOCX ZIP/XML/media validation; native Word pagination not visually verified |

Text logs have ANSI colors and trailing whitespace removed for readable Git diffs; results are unchanged. The fixture has intentionally invalid/missing fields. Its alerts are expected demonstration evidence, not failed test assertions. One attempted frontend build found a test mock's TypeScript signature error; that signature was corrected, and the final build and tests above passed. No failed assertions remain in the final runnable unit suites.

## Blocked or not executed

- **Docker/Compose/PostgreSQL:** one Docker capability check returned permission denied on the Docker API socket. The restricted operation was not retried. No PostgreSQL tests or complete Compose launch are claimed. Run the explicitly disposable PostgreSQL test procedure in UPGRADE_3.1_MAC.md.
- **Playwright:** one attempt ran with installed Chrome, one worker and max-failures=1. Chrome exited with SIGABRT before navigation and cleanup reported EPERM. The runner recorded **1 failed due to browser startup, 4 not run**, plus a teardown error. See playwright.txt. No browser test passed and no new screenshot was captured. Do not interpret the React DOM tests as a visual/mobile pass.
- **Initial native HTTP attempt with SQLite:** the production request dependency uses PostgreSQL REPEATABLE READ, which SQLite does not support, so API calls returned sanitized 503 responses (running-http.json). A verification-only dependency adapter then exercised HTTP endpoints successfully. Production database/session code was kept unchanged. The adapter was not shipped as a new production database mode.
- **Live CMS network:** not invoked for this release. The existing connector is byte-identical; 3.0 live results in older documents remain historical only.
- **User's full existing database:** not accessed. The stated 1,000 providers / 100,000 encounters / 1,000 scores and registry history must be checked with the before/after queries locally. Migration tests and unchanged core source support preservation but do not substitute for that check.
- **Remote CI run, fresh dependency installation, production performance, accessibility audit, penetration test and native Word layout review:** not performed. The installed locked-dependency environment was reused. No throughput/security certification is claimed.

## Coverage and remaining limitations

| Capability | Supporting verification |
|---|---|
| Threshold equality, fractional values, unavailable observations | Parameterized deterministic tests |
| Normal, warning, critical and failed attempts | Five-row fixture variants and recorded batch-error cases |
| Incomplete delivery versus zero errors | Failed transport/schema batches and stored-row-count mismatch tests |
| Compatible baselines | Scope, policy, source and overlapping-attempt tests |
| Warning and comparison denominators | Exact observed-value and evidence assertions |
| Repeat evaluation and rule changes | Profile reuse, cross-profile alert deduplication and historical-threshold preservation tests |
| Investigation lifecycle and assignments | Transition, resolution, reopening, invalid action, stale revision and audit consistency tests |
| Rollback and concurrency | Executed SQLite tests; dedicated PostgreSQL tests present but skipped |
| Append-only auditing | Executed SQLite migration/trigger test; PostgreSQL trigger test present but skipped |
| Read-only HTTP boundary | 405 checks for POST/PUT/PATCH/DELETE, including an untrusted X-User header |
| Configuration failure and recovery | Sanitized 503 test, post-commit hook failure isolation and bounded CLI backfill progression test |
| UI filters, evidence links, empty/error/loading, refresh | Nine executed React tests; existing race regression tests preserved |
| Mobile and full browser workflows | Playwright cases present; blocked before browser navigation |

This release intentionally has no scheduler, automatic hard-kill timeout, authenticated web triage or outbound notification integration. Backfill after monitoring outages is a documented CLI operation. Baselines need one compatible prior success but support no statistical confidence claims. Thresholds are configurable review triggers. Source-prefix membership changes do not establish actual clinician entries/exits. Event guards do not prevent a privileged database administrator from altering the schema. These limitations are visible in the documentation and interface.

## Reproduce locally

Follow UPGRADE_3.1_MAC.md for backup and no-seed migration before testing. Standard commands are `pytest -q` from backend, `npm test`, `npm run build`, and `npm run format:check` from frontend. PostgreSQL integration tests require an explicitly disposable TEST_DATABASE_URL; they intentionally reset that test schema. Browser checks require the running app, deterministic fixture history and `BASE_URL=http://127.0.0.1:8080 DATAOPS_E2E=1 npm run e2e`.

This restricted environment used `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p no:capture -q` to avoid its existing native capture issue. The application tests themselves were not disabled except for the explicitly opt-in PostgreSQL/live checks above. Save new local results separately, then update this report with what actually ran.

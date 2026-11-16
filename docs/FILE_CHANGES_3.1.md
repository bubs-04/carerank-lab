# Exact CareRank 3.1 file changes

Baseline: `351d7143b49b3f2e151d6877d0074ef050d53a60`, verified from the uploaded Git archive comment. Target branch: `feat/data-quality-monitoring`.

**12 modified files; 41 added files; no deleted files.** The complete ZIP retains every baseline source/document file. Patch includes binary additions for the guide and architecture schematic. No .env, Git metadata, database, backup, dependency directory or browser trace is included.

| Status | Exact repository path | Change |
|---|---|---|
| Modified | `.env.example` | Documents optional DQ thresholds without touching a local .env. |
| Modified | `.github/workflows/ci.yml` | Retains offline CI and adds monitoring screenshot artifact paths. |
| Modified | `README.md` | Introduces 3.1, exact baseline, safe upgrade, docs and verification boundaries. |
| Modified | `backend/app/ingestion/__main__.py` | Evaluates operator-marked interrupted attempts after their commit. |
| Modified | `backend/app/ingestion/service.py` | Calls the failure-isolated monitoring hook after existing ingestion transactions. |
| Modified | `backend/app/main.py` | Registers the read-only monitoring router and API version 3.1.0. |
| Added | `backend/app/monitoring/__init__.py` | Declares the isolated registry-monitoring package. |
| Added | `backend/app/monitoring/__main__.py` | Provides local bounded backfill, inspect and investigation commands. |
| Added | `backend/app/monitoring/api.py` | Implements eight bounded read-only endpoints and honest health states. |
| Added | `backend/app/monitoring/config.py` | Validates finite environment thresholds and automatic enable setting. |
| Added | `backend/app/monitoring/models.py` | Maps four monitoring tables, stable references and uniqueness constraints. |
| Added | `backend/app/monitoring/rules.py` | Defines twelve versioned rules, profile hashing and pure three-state decisions. |
| Added | `backend/app/monitoring/schemas.py` | Defines typed response models for rules, results, alerts, audit and trends. |
| Added | `backend/app/monitoring/service.py` | Derives evidence, selects compatible baselines, commits idempotent evaluations and performs audited investigation. |
| Modified | `backend/migrations/env.py` | Registers monitoring metadata without changing prior migrations. |
| Added | `backend/migrations/versions/003_monitoring.py` | Frozen additive schema and append-only event guards; downgrade removes monitoring only. |
| Modified | `backend/tests/test_integration.py` | Adds opt-in PostgreSQL concurrent evaluation/triage, audit guard, migration preservation and rollback tests. |
| Added | `backend/tests/test_monitoring.py` | Forty portable deterministic tests covering rule, API, CLI, transaction and migration behavior. |
| Modified | `compose.yaml` | Forwards optional DQ settings; preserves ports, volume and dependency graph. |
| Added | `docs/API_3.1.md` | Endpoint contracts, pagination, errors and local CLI lifecycle reference. |
| Added | `docs/ARCHITECTURE_3.1.md` | Architecture, transaction boundaries and audit limitations. |
| Added | `docs/CHANGELOG_3.1.md` | Meaningful release changes and preserved behavior. |
| Added | `docs/CareRank_3.1_Data_Reliability_Guide.docx` | Progressive Word learning guide with diagram and complete function inventory. |
| Added | `docs/CareRank_3.1_Data_Reliability_Guide.md` | Readable source of the Word learning guide. |
| Added | `docs/DEMO_3.1_2_MINUTES.md` | Timed engineering demo using explicit artificial fixtures. |
| Added | `docs/EXERCISES_3.1.md` | Five hands-on modification and investigation exercises. |
| Added | `docs/FILE_CHANGES_3.1.md` | This exact added/modified file inventory. |
| Added | `docs/RULES_3.1.md` | Threshold table, denominators, baseline policy, versioning and limitations. |
| Modified | `docs/SECURITY_REVIEW.md` | Corrects registry data scope and describes CLI-only triage, trust and audit boundaries. |
| Added | `docs/UPGRADE_3.1_MAC.md` | Backup, patch, no-seed upgrade, tests, diagnostics and rollback instructions. |
| Added | `docs/VERIFICATION_3.1.md` | Executed, skipped and blocked results with supporting evidence. |
| Added | `docs/architecture_3.1.png` | Explanatory architecture schematic, not an application screenshot. |
| Added | `docs/monitoring-openapi.json` | Generated OpenAPI contract for all monitoring endpoints. |
| Added | `docs/verification/v3.1/backend.txt` | Actual verification evidence: backend.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/build.txt` | Actual verification evidence: build.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/compose-config.txt` | Actual verification evidence: compose-config.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/delivery-check.json` | Actual verification evidence: delivery-check.json. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/docker.txt` | Actual verification evidence: docker.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/fixture-cli.txt` | Actual verification evidence: fixture-cli.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/format.txt` | Actual verification evidence: format.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/frontend.txt` | Actual verification evidence: frontend.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/guide-structure.json` | Actual verification evidence: guide-structure.json. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/launcher.txt` | Actual verification evidence: launcher.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/playwright.txt` | Actual verification evidence: playwright.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/preservation.json` | Actual verification evidence: preservation.json. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/ruff.txt` | Actual verification evidence: ruff.txt. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/running-http-adapter.json` | Actual verification evidence: running-http-adapter.json. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `docs/verification/v3.1/running-http.json` | Actual verification evidence: running-http.json. See VERIFICATION_3.1.md for scope and blockers. |
| Added | `frontend/e2e/monitoring.spec.ts` | Real-browser fixture workflow with read-only boundary and desktop/mobile screenshot capture. |
| Modified | `frontend/src/DataOps.tsx` | Adds monitoring area and links to exact run/findings/records while preserving Refresh status/source mode. |
| Added | `frontend/src/Monitoring.test.tsx` | Nine React tests for outcomes, loading/errors/empty states, filters, evidence links and refresh. |
| Added | `frontend/src/Monitoring.tsx` | Builds read-only monitoring dashboard, filters, charts, evidence, audit and local CLI guidance. |
| Modified | `frontend/src/styles.css` | Adds responsive monitoring states, charts, tables and investigation styling. |

The scoring/generator/pipeline/analytics implementation, CMS connector/validation/comparison, previous migrations, App mobile navigation, useApi stale-response guard and dependency manifests remain byte-identical; see verification/v3.1/preservation.json. The existing source-mode and refresh logic remains in DataOps and is covered by existing plus new tests.

The patch applies to the exact archived source tree. This isolated checkout does not reproduce the private repository’s commit history; do not replace your existing .git directory.

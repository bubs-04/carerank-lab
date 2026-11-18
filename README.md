# CareRank Lab 6.0

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![React](https://img.shields.io/badge/React-19-149ECA) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1) ![License](https://img.shields.io/badge/License-MIT-green)

CareRank is an educational healthcare data operations application with durable scheduled ingestion, authenticated analyst workflows, explainable monitoring, versioned public-registry snapshots and a separate synthetic provider-ranking workspace.

**Ranking uses fictional providers, encounters and scores. Registry data consists of public CMS source records or explicitly labeled test fixtures. Registry identities never receive synthetic scores. No patient records are ingested. CareRank is not affiliated with CMS or Garner, is not suitable for healthcare decisions, and makes no HIPAA certification claim.**

## CareRank 6.0

- Authenticated Reliability workspace: outcome rates with explicit denominators, duration percentiles, hourly activity, retries, queue age, stale leases and worker presence.
- Structured logs with validated request IDs and execution/attempt correlation; no request bodies, credentials, raw query strings or SQL parameters in application logs.
- Additive migration 007; separate owner/API/worker credentials, mounted secret files, bounded database connection/query waits, liveness and migration-aware readiness.
- Reproducible isolated PostgreSQL backup/restore, process termination, database crash recovery and synthetic query measurements.
- Local demo launcher with private random development accounts and an isolated, guarded reset. Optional checksum-verified public CMS archives are explicitly labeled as archived, never fresh retrieval.
- Production Compose, AWS reference template and a manual release-review workflow. No AWS resources have been created; this is not a production certification.

[Release evidence and limitations](docs/RELEASE_6.0.md) · [Operational architecture](docs/ARCHITECTURE_6.0.md) · [Six-minute Garner demonstration](docs/DEMO_6.0.md) · [Cloud deployment runbook](infra/README.md)

Start the isolated localhost demo with `python3 scripts/demo.py start`. Open `http://127.0.0.1:8086`; credentials remain in ignored `.demo/accounts.json`. The current environment blocks `data.cms.gov`; a genuine CMS archive is **not bundled**, and the live-CMS portion remains a release limitation. Fixture demonstrations work offline after dependencies/images are installed.

## Retained CareRank 5.0 capabilities

- PostgreSQL-backed pipeline definitions, execution attempts and append-only history; no additional queue infrastructure.
- Configurable interval schedules, authenticated manual runs, cancellation, bounded exponential retries, independent worker heartbeats, leases and interrupted-work recovery.
- At-least-once delivery with fenced, idempotent snapshot publication and durable monitoring reconciliation. Execution attempts remain visible even when publication reuses an existing snapshot.
- Pipeline Operations workspace with schedule policies, status filters, metrics, attempt timelines, failure codes and links to ingestion/quality evidence.
- Administrator-only configuration; Analysts and Administrators can trigger, cancel and retry; Viewers can inspect. Existing session, CSRF, account-revision and incident controls remain in force.
- Separate API, worker and migration/operator database credentials. Migration 006 adds four tables without replacing existing application data.
- Offline fixture workflows, including a development-only first-attempt failure followed by automatic recovery. Live CMS requests are an explicit source choice.

[Architecture and reliability boundary](docs/ARCHITECTURE_5.0.md) · [Changelog, demonstration and verification status](docs/RELEASE_5.0.md) · [Authentication threat model](docs/SECURITY_4.0.md)

Earlier release reports under `docs/` are historical evidence, not current verification claims.

## Existing installation: preserve history

Back up your database and retain your `.env` and database volume. Generate any missing API/worker credentials, build the updated images, migrate through 007, apply the restricted runtime grants, then restart the API, worker and web services. Do not run `app.pipeline` or a benchmark on a database whose synthetic data must be preserved; those are explicit dataset replacement tools.

```bash
make setup
docker compose build
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps runtime
docker compose up -d --no-deps api worker web
```

Migration 006 adds `pipeline_definitions`, `pipeline_executions`, `pipeline_attempts` and `pipeline_events`, indexes and append-only event protection. Migrations 004/005 and all existing synthetic, registry, monitoring and identity rows remain intact. Migration 006 refuses downgrade outside disposable `carerank_test`; use forward corrections for retained databases. No migration creates default accounts or schedules.

Migration 007 adds transient `pipeline_workers` presence and history/metric indexes. Only presence older than seven days is pruned; durable executions and audit records are retained. Migration 007 also refuses downgrade outside `carerank_test`. Use the same upgrade/grant procedure above.

## Local development with Docker Compose

Docker Compose uses secure authentication defaults. For localhost HTTP development, add these explicit settings to your ignored `.env` before startup:

```dotenv
APP_ENV=development
AUTH_COOKIE_SECURE=false
AUTH_ALLOWED_ORIGINS=http://localhost:8080
```

Use the exact hostname selected above in the browser. Do not use these HTTP cookie settings for a shared or internet deployment.

```bash
make up
# Generates missing, distinct owner/API/worker passwords without replacing existing settings,
# migrates, seeds a pristine lab only, provisions grants and starts localhost services.
```

Create accounts interactively; passwords are read without echo and are never command-line arguments:

```bash
docker compose run --rm --no-deps -e APP_ENV=development seed python -m app.auth create-user \
  --username analyst --display-name 'Development Analyst' --role analyst
docker compose run --rm --no-deps -e APP_ENV=development seed python -m app.auth create-user \
  --username administrator --display-name 'Development Administrator' --role administrator
docker compose run --rm --no-deps -e APP_ENV=development seed python -m app.auth create-user \
  --username viewer --display-name 'Development Viewer' --role viewer
```

Passwords require 12–256 characters. Choose unique passwords. Provisioning refuses to run unless `APP_ENV=development`; it does not overwrite an existing account. Sign in at `http://localhost:8080`. Health remains public at `/api/health`; all ranking, analytics and registry data require a session. `make down` retains the named volume.

For production planning, read [the security deployment boundary](docs/SECURITY_4.0.md). The development account command is not a production identity-management system. No deployment is performed by these changes.

## Published cloud development environment

```bash
bash /workspace/.carerank/start.sh
source /workspace/.carerank/session.sh
cd /workspace/carerank-lab
```

The published installation scripts are environment assets. The helper retains the protected 401 readiness check and explicit local HTTP development cookie/origin settings. The CareRank 5.0 correction provisions a separate worker role and starts the worker supervisor alongside the restricted API. The helper strips owner/test and unrelated runtime credentials from child environments. Its private worker connection is stored in `/workspace/.carerank/worker-runtime.env`. `session.sh` retains operator credentials for migrations and test administration; it is not an API or worker launch environment. Restart processes after code/configuration changes. Destructive verification stays on `carerank_test`; retained development data stays in `carerank`.

Runtime credential files under `/workspace/.carerank/` and `/workspace/.carerank/accounts-4.0.json` are private environment assets. Keep them owner-readable only and excluded from the repository and verification artifacts.

## Native development

Use Python 3.12, Node 24.15+ and PostgreSQL 16. Install locked dependencies and supply your local database credentials through environment variables. Never commit them.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql+psycopg://OWNER:OWNER_PASSWORD@127.0.0.1:5432/carerank'
export RUNTIME_DATABASE_URL='postgresql+psycopg://carerank_api:REPLACE_WITH_RANDOM_API_PASSWORD_24PLUS@127.0.0.1:5432/carerank'
export WORKER_DATABASE_URL='postgresql+psycopg://carerank_worker:REPLACE_WITH_RANDOM_WORKER_PASSWORD_24PLUS@127.0.0.1:5432/carerank'
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank_test'
export APP_ENV=development AUTH_COOKIE_SECURE=false
export AUTH_ALLOWED_ORIGINS=http://127.0.0.1:5173
cd backend
alembic upgrade head
python -m app.bootstrap
python -m app.runtime_role
python -m app.auth create-user --username analyst --display-name 'Development Analyst' --role analyst
env -u TEST_DATABASE_URL -u POSTGRES_PASSWORD -u RUNTIME_DATABASE_URL -u WORKER_DATABASE_URL \
  DATABASE_URL="$RUNTIME_DATABASE_URL" AUTH_TRUSTED_PROXIES=127.0.0.1/32,::1/128 \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

In a second operator shell, load the same private configuration and start the worker from `backend/`:

```bash
env -u TEST_DATABASE_URL -u POSTGRES_PASSWORD -u RUNTIME_DATABASE_URL -u WORKER_DATABASE_URL \
  DATABASE_URL="$WORKER_DATABASE_URL" python -m app.operations worker
```

In another shell, run `npm ci` and `npm run dev` from `frontend/`. Vite proxies `/api` to the API and overwrites its client-address header; open `http://127.0.0.1:5173`. The trusted loopback setting assumes other local processes are trusted operators. Compose instead trusts only its private Nginx address and publishes only the web port. Do not broaden the trusted proxy list to arbitrary clients.

## Pipeline operations

Sign in and open **Pipeline operations**. An Administrator creates a definition with its source, requested rows, interval, maximum attempts, initial backoff and per-attempt timeout. Definitions start paused unless explicitly enabled; enabling makes the first occurrence due immediately. Pausing stops future scheduling and leaves already queued/running work intact. Use cancellation separately when needed.

The worker schedules and executes from PostgreSQL. Multiple worker processes can share the queue; a definition has at most one running execution. Missed intervals coalesce into one occurrence rather than a catch-up storm. Bounds are 100 definitions and 20 active executions per definition; a saturated schedule records `schedule_deferred` and advances to its next interval. See [the architecture](docs/ARCHITECTURE_5.0.md) for precise retry, lease and publication semantics.

```bash
# Compose starts this service automatically; inspect operational output:
docker compose logs --tail=100 worker
# One scheduling/recovery/reconciliation pass, without fetching new source data:
docker compose run --rm --no-deps worker python -m app.operations tick
# Execute at most one eligible attempt, including scheduling/recovery first:
docker compose run --rm --no-deps worker python -m app.operations worker --once
```

An Analyst or Administrator can run a paused pipeline manually, cancel active unpublished work with a reason, or retry a terminal failed/timed-out/cancelled execution. Retry creates a new execution and retains the old evidence; a recorded publication is resumed without refetching. Cancellation after publication returns 409 because monitoring reconciliation still needs to finish. The dashboard exposes the attempt history and evidence links; existing alert investigation remains in Data operations.

## Data operations

The twelve versioned rules distinguish missing evidence from zero errors and compare only compatible source, scope and validation-policy histories. Authenticated viewers can inspect evidence. Analysts and administrators can record a required decision note, change allowed lifecycle states, assign an active analyst/administrator, or clear an assignment. A stale revision returns a conflict instead of overwriting another analyst's decision.

Direct ingestion and evaluation backfill remain operator commands; the web pipeline controls use the separate restricted worker. Synthetic replacement remains an explicit operator-only tool:

```bash
docker compose run --rm --no-deps seed python -m app.ingestion --max-rows 1000
docker compose run --rm --no-deps seed python -m app.monitoring evaluate --mode cms --limit 100
# Offline artificial registry fixtures:
docker compose run --rm --no-deps seed python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5
docker compose run --rm --no-deps seed python -m app.ingestion --fixture tests/fixtures/cms_registry_b.csv --max-rows 5
```

The bounded CMS source-order prefix is not a representative national census. Sample membership changes do not establish actual clinician arrivals/departures. Monitoring alerts are review signals, not clinical quality assessments. See [rule definitions](docs/RULES_3.1.md), [registry source guide](docs/CareRank_3.0_Data_Engineering_Guide.md) and [monitoring guide](docs/CareRank_3.1_Data_Reliability_Guide.md).

## Ranking and analytics

The existing fictional lab includes 1,000 providers and 100,000 encounters across five specialties. SQL aggregates evidence; a deterministic formula combines risk-adjusted outcome residuals (60%), normalized costs (25%), reliability (10%) and volume (5%). Scores require at least 30 observed outcomes and 80% completeness. Missing evidence stays explicit. Specialty ranks and provider comparisons remain within one specialty.

The dashboard, search and pagination, provider profiles, component comparisons, cohort cost/quality chart, completeness analysis, snapshot comparisons, mobile navigation and Refresh status remain available after sign-in. No authentication feature changes the scoring formula or joins registry identities to synthetic providers.

## Verification

```bash
make lint
make test
cd frontend && npm run format:check
```

PostgreSQL integration tests require the separate disposable `carerank_test` database. They reset its schema and must never target `carerank`. Existing portable unit tests also use temporary SQLite databases. Live CMS tests remain explicitly opt-in.

Browser tests require a running isolated test stack, fixture history and development accounts. Supply `E2E_USERNAME`/`E2E_PASSWORD` for the analyst and the corresponding `E2E_VIEWER_USERNAME`/`E2E_VIEWER_PASSWORD` and `E2E_ADMIN_USERNAME`/`E2E_ADMIN_PASSWORD` credentials through the test environment. Do not use personal account passwords. Set `DATAOPS_E2E=1` and `CHROMIUM_PATH` for the installed browser. Browser lifecycle actions are writes: point the test API at `carerank_test` to preserve development incidents and audit history.

The CI workflow creates disposable credentials, runs tests against `carerank_test`, provisions distinct restricted API/worker roles, exercises Nginx from two distinct clients, and retains browser evidence. Pipeline browser recovery requires a worker using that same test database. Actual results and any unexecuted checks are recorded with [the 5.0 delivery](docs/RELEASE_5.0.md).

## API and troubleshooting

Authentication endpoints are `/api/auth/login`, `/api/auth/me` and `/api/auth/logout`. A session cookie authenticates requests. Mutations require both an allowed `Origin` and `X-CSRF-Token` from the authenticated session response. Analyst actions use `POST /api/dataops/monitoring/alerts/{id}/actions`; account role/activation changes use administrator-only `PATCH /api/auth/users/{id}` with the current `expected_revision` and only intentionally changed `role` or `active` fields. A stale account update returns 409; the UI reloads the account for review before a deliberate retry. Pipeline APIs live under `/api/operations`: `/pipelines` for definitions, `/pipelines/{id}/trigger` for manual runs and `/executions` for history, detail, cancellation and retry. Trigger/retry requests require a UUID `idempotency_key`; retries and changes also carry `expected_revision`. Reuse a key after an uncertain network response. Public documentation at `/docs` describes the contracts; authorization is enforced on actual requests.

- **401:** sign in again; the account may be inactive or its session expired/revoked.
- **403:** check the role, CSRF token, and exact allowed origin. Do not broaden origins to bypass an error.
- **409:** another decision changed the revision; refresh and review it before submitting again.
- **429:** wait for the login limit's retry interval before retrying.
- **Cookie absent on HTTP:** explicitly select development mode and disable Secure cookies for the local HTTP process only.
- **Database/schema error:** check the local database and run `alembic upgrade head`; never let the API create schema ad hoc.

## Limitations

This implementation supports local accounts and server sessions, not enterprise SSO/MFA or production account recovery. Shared tenancy, external notifications, cron/calendar schedules, arbitrary connector plugins, malware scanning, privileged-database tamper resistance and formal compliance certification are outside this release. Pipeline execution requires a running worker and healthy PostgreSQL; leases make interrupted work recoverable, not highly available by themselves. This release makes no exactly-once execution claim. Reverse-proxy TLS, deployment-specific secret management and runtime/owner credential delivery, backup/restore testing and operational monitoring remain release blockers before a shared deployment. Local credential separation does not establish those production controls. The [threat model](docs/SECURITY_4.0.md) identifies the implemented controls and residual risks.

AI assisted implementation, documentation and the explicitly reported tests. No independent human security audit is claimed. MIT licensed.

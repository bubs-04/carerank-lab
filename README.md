# CareRank Lab 4.0

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![React](https://img.shields.io/badge/React-19-149ECA) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1) ![License](https://img.shields.io/badge/License-MIT-green)

CareRank is an educational healthcare data operations application with authenticated analyst workflows, explainable monitoring, versioned public-registry snapshots and a separate synthetic provider-ranking workspace.

**Ranking uses fictional providers, encounters and scores. Registry data consists of public CMS source records or explicitly labeled test fixtures. Registry identities never receive synthetic scores. No patient records are ingested. CareRank is not affiliated with CMS or Garner, is not suitable for healthcare decisions, and makes no HIPAA certification claim.**

## CareRank 4.0

- Password authentication with salted scrypt hashes, opaque server-side sessions, absolute expiration, logout, secure cookie defaults and CSRF checks.
- Backend-enforced Administrator, Analyst and Viewer roles. Every application data endpoint requires a valid active account.
- Administrator workspace for reviewing accounts, changing roles or activation, and inspecting security events. Account changes require the reviewed account revision, revoke affected sessions, and append prior/new access state to the audit trail.
- An analyst investigation queue with severity/state filters, assignments, decisions, resolution, reopening and chronological audit history.
- Investigation actions tied to authenticated account IDs; historical system/CLI audit records retain their original attribution.
- Bounded persistent login throttling with independent account/client limits, trusted proxy client addresses, exact allowed origins, response security headers and explicit development provisioning.
- Separate restricted API database credentials and privileged migration/operator credentials in Compose, CI and the cloud development runtime.
- Additive migrations 004 and 005 preserve synthetic data, snapshots, alerts and previous audit events. Initial Compose seeding skips any existing synthetic data or run history.

[Architecture and diagrams](docs/ARCHITECTURE_4.0.md) · [Security and threat model](docs/SECURITY_4.0.md) · [Changelog](docs/CHANGELOG_4.0.md) · [Five-minute demonstration](docs/DEMO_4.0_5_MINUTES.md)

Current executed checks, screenshots and limitations are recorded in [the 4.0 verification report](docs/VERIFICATION_4.0.md). Earlier release reports under `docs/` are historical evidence, not current verification claims.

## Existing installation: preserve history

Back up your database and retain your `.env` and database volume. Generate any missing runtime credential, build the updated images, migrate through 005, apply the restricted runtime grants, then restart the API and web services. Do not run `app.pipeline` or a benchmark on a database whose synthetic data must be preserved; those are explicit dataset replacement tools.

```bash
make setup
docker compose build
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps runtime
docker compose up -d --no-deps api web
```

Migration 004 adds account/session/security-event tables and nullable identity references to monitoring records. Migration 005 adds a durable account revision and an indexed throttle-expiry lookup. Existing accounts start at revision 1; existing data and audit rows are retained. Migration 005 refuses downgrade outside disposable `carerank_test`, so retain a backup and use forward corrections for retained databases. Neither migration creates default credentials. Provision development accounts as below.

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
# Generates missing, distinct owner/API passwords without replacing existing settings,
# migrates, seeds a pristine lab only, provisions API grants and starts localhost services.
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

The published installation scripts are environment assets. This security correction updates the cloud helper to expect 401 from an anonymous provider request, preserving authorization. It also provisions a separate runtime role and launches the API with that connection while removing owner/test credential variables from the child process. The helper explicitly configures local HTTP development cookies, allowed origins and the trusted loopback Vite proxy. `session.sh` retains operator credentials for migration and test administration; it is not an API launch environment. Restart the API after code/configuration changes. Destructive verification stays on `carerank_test`; retained development data stays in `carerank`.

The runtime connection is stored only in `/workspace/.carerank/api-runtime.env`; account credentials are stored only in `/workspace/.carerank/accounts-4.0.json`. Both have owner-only permissions and are excluded from the repository and verification artifacts.

## Native development

Use Python 3.12, Node 24.15+ and PostgreSQL 16. Install locked dependencies and supply your local database credentials through environment variables. Never commit them.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql+psycopg://OWNER:OWNER_PASSWORD@127.0.0.1:5432/carerank'
export RUNTIME_DATABASE_URL='postgresql+psycopg://carerank_api:DISTINCT_RANDOM_PASSWORD@127.0.0.1:5432/carerank'
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank_test'
export APP_ENV=development AUTH_COOKIE_SECURE=false
export AUTH_ALLOWED_ORIGINS=http://127.0.0.1:5173
cd backend
alembic upgrade head
python -m app.bootstrap
python -m app.runtime_role
python -m app.auth create-user --username analyst --display-name 'Development Analyst' --role analyst
env -u TEST_DATABASE_URL -u POSTGRES_PASSWORD -u RUNTIME_DATABASE_URL \
  DATABASE_URL="$RUNTIME_DATABASE_URL" AUTH_TRUSTED_PROXIES=127.0.0.1/32,::1/128 \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

In another shell, run `npm ci` and `npm run dev` from `frontend/`. Vite proxies `/api` to the API and overwrites its client-address header; open `http://127.0.0.1:5173`. The trusted loopback setting assumes other local processes are trusted operators. Compose instead trusts only its private Nginx address and publishes only the web port. Do not broaden the trusted proxy list to arbitrary clients.

## Data operations

The twelve versioned rules distinguish missing evidence from zero errors and compare only compatible source, scope and validation-policy histories. Authenticated viewers can inspect evidence. Analysts and administrators can record a required decision note, change allowed lifecycle states, assign an active analyst/administrator, or clear an assignment. A stale revision returns a conflict instead of overwriting another analyst's decision.

External ingestion, evaluation backfill and synthetic replacement remain local operator commands, separate from web roles:

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

The CI workflow creates disposable credentials, runs tests against `carerank_test`, provisions a restricted browser-test runtime role, exercises Nginx from two distinct clients, and retains browser evidence. Actual results and any unexecuted checks belong in [VERIFICATION_4.0.md](docs/VERIFICATION_4.0.md).

## API and troubleshooting

Authentication endpoints are `/api/auth/login`, `/api/auth/me` and `/api/auth/logout`. A session cookie authenticates requests. Mutations require both an allowed `Origin` and `X-CSRF-Token` from the authenticated session response. Analyst actions use `POST /api/dataops/monitoring/alerts/{id}/actions`; account role/activation changes use administrator-only `PATCH /api/auth/users/{id}` with the current `expected_revision` and only intentionally changed `role` or `active` fields. A stale account update returns 409; the UI reloads the account for review before a deliberate retry. Public documentation at `/docs` describes the contracts; authorization is enforced on actual requests.

- **401:** sign in again; the account may be inactive or its session expired/revoked.
- **403:** check the role, CSRF token, and exact allowed origin. Do not broaden origins to bypass an error.
- **409:** another decision changed the revision; refresh and review it before submitting again.
- **429:** wait for the login limit's retry interval before retrying.
- **Cookie absent on HTTP:** explicitly select development mode and disable Secure cookies for the local HTTP process only.
- **Database/schema error:** check the local database and run `alembic upgrade head`; never let the API create schema ad hoc.

## Limitations

This implementation supports local accounts and server sessions, not enterprise SSO/MFA or production account recovery. Shared tenancy, external notifications, scheduled ingestion, malware scanning, privileged-database tamper resistance and formal compliance certification are outside this release. Reverse-proxy TLS, deployment-specific secret management and runtime/owner credential delivery, backup/restore testing and operational monitoring remain release blockers before a shared deployment. Local credential separation does not establish those production controls. The [threat model](docs/SECURITY_4.0.md) identifies the implemented controls and residual risks.

AI assisted implementation, documentation and the explicitly reported tests. No independent human security audit is claimed. MIT licensed.

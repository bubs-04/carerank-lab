# CareRank Lab 4.0

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![React](https://img.shields.io/badge/React-19-149ECA) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1) ![License](https://img.shields.io/badge/License-MIT-green)

CareRank is an educational healthcare data operations application with authenticated analyst workflows, explainable monitoring, versioned public-registry snapshots and a separate synthetic provider-ranking workspace.

**Ranking uses fictional providers, encounters and scores. Registry data consists of public CMS source records or explicitly labeled test fixtures. Registry identities never receive synthetic scores. No patient records are ingested. CareRank is not affiliated with CMS or Garner, is not suitable for healthcare decisions, and makes no HIPAA certification claim.**

## CareRank 4.0

- Password authentication with salted scrypt hashes, opaque server-side sessions, absolute expiration, logout, secure cookie defaults and CSRF checks.
- Backend-enforced Administrator, Analyst and Viewer roles. Every application data endpoint requires a valid active account.
- Administrator workspace for reviewing accounts, changing roles or activation, and inspecting security events. Account changes revoke affected sessions.
- An analyst investigation queue with severity/state filters, assignments, decisions, resolution, reopening and chronological audit history.
- Investigation actions tied to authenticated account IDs; historical system/CLI audit records retain their original attribution.
- Persistent login throttling, exact allowed origins, response security headers, revision-conflict handling and explicit account provisioning for development.
- Additive migration 004 preserves synthetic data, snapshots, alerts and previous audit events. Initial Compose seeding skips any existing synthetic data or run history.

[Architecture and diagrams](docs/ARCHITECTURE_4.0.md) · [Security and threat model](docs/SECURITY_4.0.md) · [Changelog](docs/CHANGELOG_4.0.md) · [Five-minute demonstration](docs/DEMO_4.0_5_MINUTES.md)

Current executed checks, screenshots and limitations are recorded in [the 4.0 verification report](docs/VERIFICATION_4.0.md). Earlier release reports under `docs/` are historical evidence, not current verification claims.

## Existing installation: preserve history

Back up your database and retain your `.env` and database volume. Build the updated images, run migration 004, then restart the API and web services. Do not run `app.pipeline` or a benchmark on a database whose synthetic data must be preserved; those are explicit dataset replacement tools.

```bash
docker compose build
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps api web
```

Migration 004 adds account/session/security-event tables and nullable identity references to existing monitoring records. It does not create default credentials. Provision development accounts as below. Downgrading 004 removes authentication and identity-reference columns; preserve a backup before any rollback. Prior alert/audit records are retained, but a downgrade discards their new identity metadata.

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
# Creates a random PostgreSQL password if .env does not exist, migrates,
# seeds a pristine synthetic lab only, and starts localhost services.
```

Create accounts interactively; passwords are read without echo and are never command-line arguments:

```bash
docker compose run --rm --no-deps api python -m app.auth create-user \
  --username analyst --display-name 'Development Analyst' --role analyst
docker compose run --rm --no-deps api python -m app.auth create-user \
  --username administrator --display-name 'Development Administrator' --role administrator
docker compose run --rm --no-deps api python -m app.auth create-user \
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

The published installation scripts are environment assets. Set `APP_ENV=development`, `AUTH_COOKIE_SECURE=false` and exact allowed origins in the API process environment when using local HTTP. Restart the API after changing application code or authentication settings. Keep destructive verification on `carerank_test`; the running development database is `carerank`.

The older published startup script's final unauthenticated `/api/providers` probe returns 401 after upgrading to 4.0. The database/API health probes remain valid; verify provider access after signing in. Do not remove authorization to satisfy that old probe. This integration leaves the persistent installation scripts unchanged. Development credentials provisioned in the current cloud workspace are stored only in `/workspace/.carerank/accounts-4.0.json` with owner-only permissions; they are not part of the repository or verification artifacts.

## Native development

Use Python 3.12, Node 24.15+ and PostgreSQL 16. Install locked dependencies and supply your local database credentials through environment variables. Never commit them.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank'
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank_test'
export APP_ENV=development AUTH_COOKIE_SECURE=false
export AUTH_ALLOWED_ORIGINS=http://127.0.0.1:5173
cd backend
alembic upgrade head
python -m app.bootstrap
python -m app.auth create-user --username analyst --display-name 'Development Analyst' --role analyst
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

In another shell, run `npm ci` and `npm run dev` from `frontend/`. Vite proxies `/api` to the API; open `http://127.0.0.1:5173`.

## Data operations

The twelve versioned rules distinguish missing evidence from zero errors and compare only compatible source, scope and validation-policy histories. Authenticated viewers can inspect evidence. Analysts and administrators can record a required decision note, change allowed lifecycle states, assign an active analyst/administrator, or clear an assignment. A stale revision returns a conflict instead of overwriting another analyst's decision.

External ingestion, evaluation backfill and synthetic replacement remain local operator commands, separate from web roles:

```bash
docker compose run --rm --no-deps api python -m app.ingestion --max-rows 1000
docker compose run --rm --no-deps api python -m app.monitoring evaluate --mode cms --limit 100
# Offline artificial registry fixtures:
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_b.csv --max-rows 5
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

The CI workflow creates disposable credentials, runs tests against `carerank_test`, and retains browser evidence. Actual results and any unexecuted checks belong in [VERIFICATION_4.0.md](docs/VERIFICATION_4.0.md).

## API and troubleshooting

Authentication endpoints are `/api/auth/login`, `/api/auth/me` and `/api/auth/logout`. A session cookie authenticates requests. Mutations require both an allowed `Origin` and `X-CSRF-Token` from the authenticated session response. Analyst actions use `POST /api/dataops/monitoring/alerts/{id}/actions`; account role/activation changes use administrator-only `PATCH /api/auth/users/{id}`. Public documentation at `/docs` describes the contracts; authorization is enforced on actual requests.

- **401:** sign in again; the account may be inactive or its session expired/revoked.
- **403:** check the role, CSRF token, and exact allowed origin. Do not broaden origins to bypass an error.
- **409:** another decision changed the revision; refresh and review it before submitting again.
- **429:** wait for the login limit's retry interval before retrying.
- **Cookie absent on HTTP:** explicitly select development mode and disable Secure cookies for the local HTTP process only.
- **Database/schema error:** check the local database and run `alembic upgrade head`; never let the API create schema ad hoc.

## Limitations

This implementation supports local accounts and server sessions, not enterprise SSO/MFA or production account recovery. Shared tenancy, external notifications, scheduled ingestion, malware scanning, privileged-database tamper resistance and formal compliance certification are outside this release. Reverse-proxy TLS, secret management, least-privilege database credentials, backup/restore testing and operational monitoring must be configured before a shared deployment. The [threat model](docs/SECURITY_4.0.md) identifies the implemented controls and residual risks.

AI assisted implementation, documentation and the explicitly reported tests. No independent human security audit is claimed. MIT licensed.

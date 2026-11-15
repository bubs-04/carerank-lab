# CareRank Lab

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![React](https://img.shields.io/badge/React-19-149ECA) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1) ![License](https://img.shields.io/badge/License-MIT-green)

An independent educational healthcare provider intelligence platform: reproducible synthetic data, transactional SQL processing, explainable specialty rankings, and a React dashboard.

**All providers, encounters, outcomes and scores are fictional. This project is not affiliated with Garner and does not reproduce its proprietary methodology. Never use these scores for healthcare decisions.**

## Features

- 1,000 synthetic providers and 100,000 encounters across five specialties by default.
- Strict schema and duplicate checks; missing outcomes are tracked, not imputed.
- Atomic dataset replacement, writer lock, durable run audit and safe reruns.
- Risk-adjusted outcome residuals, normalized costs, shrinkage and minimum evidence thresholds.
- Dashboard, provider search, specialty/location/quality/cost filters, pagination, profile and same-specialty comparison.
- OpenAPI, Alembic migrations, pytest, Vitest, live full-stack DOM workflow and Playwright browser workflow.

## Architecture

```mermaid
flowchart TD
  UI[React and TypeScript] --> Proxy[Vite or Nginx]
  Proxy --> API[FastAPI read API]
  API --> DB[(PostgreSQL)]
  CLI[Python pipeline CLI] --> V[Generate and validate]
  V --> SQL[Transactional load and SQL aggregation]
  SQL --> S[Score and rank by specialty]
  S --> DB
```

## Quick start with Docker Compose

Prerequisites: Git, Python 3.12+ for setup, Docker Desktop or Docker Engine with Compose v2, and Make. Windows users can run the commands in WSL2. No paid services or API keys are needed.

```bash
git clone <YOUR_REPOSITORY_URL>
cd carerank-lab
make up
# Dashboard: http://localhost:8080
# Swagger: http://localhost:8000/docs
# Health: http://localhost:8000/api/health
```

`make up` generates a random password in ignored `.env`, builds images, waits for PostgreSQL, migrates, seeds the dataset, starts the API and then Nginx. First startup can take several minutes. Credentials never enter frontend bundles. Services bind only to localhost; PostgreSQL is not published to the host.

```bash
make pipeline                       # replace demo dataset using the default seed
# configurable rerun:
docker compose run --rm seed python -m app.pipeline --providers 500 --encounters 50000 --seed 7
make down                           # stop; retain named database volume
make rebuild                        # rebuild images without cache
```

## Native development

Install Python 3.12+, Node 24.15+ and PostgreSQL 16. Create two empty databases, `carerank` and `carerank_test`, using your PostgreSQL account. Set the connection URLs to your own local credentials; URL-encode special password characters.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank'
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/carerank_test'
cd backend
alembic upgrade head
python -m app.pipeline
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```bash
cd carerank-lab/frontend
npm ci
npm run dev
# http://localhost:5173; /api is proxied to port 8000
```

## Tests and measurements

```bash
make test                 # Python tests + frontend unit tests + production build
make lint                 # Python lint and formatting
cd frontend && npm run format:check
# From repository root, with API and Vite running:
cd frontend && LIVE_URL=http://127.0.0.1:5173 npm test
npx playwright install chromium
npm run e2e               # browser workflow, generates screenshots in docs/
# Against the demo database only; replaces its dataset:
cd ../backend && python -m app.benchmark
```

Integration tests require `TEST_DATABASE_URL` and replace data there. Without it, PostgreSQL integration tests are explicitly skipped. The live DOM test is skipped unless `LIVE_URL` is set. Playwright uses port 5173 by default; use `BASE_URL=http://localhost:8080 npm run e2e` for Compose.

See [verification report](docs/IMPLEMENTATION_VERIFICATION_REPORT.md), [raw benchmark](docs/benchmark.json), and test result logs. Docker and browser execution limitations are recorded, not represented as passing checks. GitHub Actions is configured to exercise Compose and Playwright on a normal runner; it has not run remotely yet.

## Screenshots

The Playwright workflow writes `docs/overview.png`, `docs/explorer.png`, `docs/comparison.png`, `docs/provider-profile.png`, and `docs/mobile.png`. Browser launch was blocked in the build environment, so screenshots are not included or fabricated. Run the command above locally, inspect the images, then add them to this README before publication.

## API examples

```bash
curl 'http://localhost:8000/api/providers?specialty=Cardiology&page=1&page_size=12'
curl 'http://localhost:8000/api/providers?q=Demo&min_quality=45&max_cost=700&sort=cost'
curl 'http://localhost:8000/api/providers/1'
curl 'http://localhost:8000/api/compare?ids=1&ids=6'
curl 'http://localhost:8000/api/analytics'
curl 'http://localhost:8000/api/pipeline'
```

Comparison accepts two or three distinct providers within one specialty. Bad parameters return 422, missing providers 404, and database failures 503. The API is deliberately read-only; pipeline execution requires CLI access.

## Technical decisions

Synchronous SQLAlchemy keeps a small database-backed API easy to follow. PostgreSQL does set-based normalization and aggregation; Python owns deterministic generation and scoring. Scores are stored to keep reads cheap. Alembic owns schema evolution. Full replacement with a transaction is appropriate for this bounded demo; it is not a production claims ingestion strategy. Custom CSS and semantic HTML avoid an oversized UI framework. No dbt, Airflow, AWS, dlt or Kubernetes: one local pipeline does not justify their operational overhead.

## Documentation and learning

- [Complete technical guide](docs/CareRank_Lab_Complete_Technical_Guide.md)
- [Interview preparation](docs/CareRank_Lab_Interview_Preparation.md)
- [Exercises](docs/EXERCISES.md) and [separate solutions](docs/EXERCISE_SOLUTIONS.md)
- [GitHub portfolio guide](GITHUB_PORTFOLIO_GUIDE.md)
- [Security review](docs/SECURITY_REVIEW.md)
- Word editions of the technical and interview guides are in `docs/`.

## Troubleshooting

- Database refused: check the URI, database existence and PostgreSQL service; Compose users run `docker compose ps` and `docker compose logs db`.
- Missing tables: run `alembic upgrade head` in `backend/`; do not use ad hoc `create_all` in the API.
- Empty UI: run the pipeline, then inspect `/api/pipeline` and `/api/analytics`.
- Port conflict: stop the conflicting service or change host ports in Compose. Native Vite proxies to 8000; set `API_PROXY` if you change it.
- No test data: verify `TEST_DATABASE_URL` points to a separate disposable database.
- Changed `.env` password with an existing volume: the initialized database retains its old password. Restore the original local password or deliberately recreate only this demo volume after accepting data loss.
- A run stuck at `running`: a process crash can leave the audit unfinished. Check that no pipeline is active before investigating; automated stale-run recovery is not implemented.
- Node build failure: use Node 24.15+ and `npm ci`; do not discard the lockfile to mask incompatibilities.

## Limitations and roadmap

No authentication, authorization, clinical validation, patient-level longitudinal analysis, uncertainty intervals, fairness audit, real provider matching, or production operations. The mean score and mixed-specialty list are descriptive; only specialty ranks are comparable. Future work: outcome calibration, uncertainty, versioned snapshots, incremental ingestion, role-based access, cloud secrets, monitoring and clinically governed validation.

## AI assistance

ChatGPT generated the implementation, tests and documentation, then executed the checks described in the verification report. Prabhat supplied the scope and learning goals. No independent human code review or hands-on modification by Prabhat is claimed. See the exercises before presenting the project as understood. MIT licensed.

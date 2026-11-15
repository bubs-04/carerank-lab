# CareRank Lab 2.0

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![React](https://img.shields.io/badge/React-19-149ECA) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1) ![License](https://img.shields.io/badge/License-MIT-green)

An independent educational healthcare provider intelligence platform: reproducible synthetic data, transactional SQL processing, explainable specialty rankings, and a React dashboard.

**All providers, encounters, outcomes and scores are fictional. This project is not affiliated with Garner and does not reproduce its proprietary methodology. Never use these scores for healthcare decisions.**

## Existing installation: upgrade safely

Follow [the 2.0 Mac upgrade guide](docs/UPGRADE_2.0_MAC.md). It keeps your original project directory, `.env` and database volume, and rebuilds only API/web with `--no-deps`. No migration or reseeding is needed. Do not use the fresh-install commands below to upgrade an existing dataset.

[Engineering walkthrough](docs/CareRank_Lab_2.0_Engineering_Walkthrough.docx) · [Changelog](docs/CHANGELOG_2.0.md) · [2-minute demo](docs/DEMO_SCRIPT_2_MINUTES.md) · [2.0 verification](docs/VERIFICATION_2.0.md)

## Start here on a Mac (fresh installation)

Use [Mac setup](docs/MAC_SETUP_GUIDE.md) and the [beginner guide](docs/CareRank_Lab_Beginners_Guide.docx). From the extracted project root, with Docker Desktop running:

```bash
bash scripts/start_mac.sh
```

This path uses the Mac's shell and OpenSSL and does not require host Python or Make. If you already have the original app running, follow [Apply the 2.0 update](docs/UPGRADE_2.0_MAC.md); preserve your existing `.env` and database volume.

[Historical 1.x Mac review results](docs/MAC_VERIFICATION_REPORT.md) distinguish new checks from the historical Linux build. The user reported opening the original site and comparing providers locally; this is a manual report, not an automated browser pass for the updated code.

## Features

- 1,000 synthetic providers and 100,000 encounters across five specialties by default.
- Strict schema and duplicate checks; missing outcomes are tracked, not imputed.
- Atomic dataset replacement, writer lock, durable run audit and safe reruns.
- Risk-adjusted outcome residuals, normalized costs, shrinkage and minimum evidence thresholds.
- Dashboard, provider search, specialty/location/quality/cost filters, pagination, profile and same-specialty comparison.
- OpenAPI, Alembic migrations, pytest, Vitest, live full-stack DOM workflow and Playwright browser workflow.

## The engineering problem

A provider list alone hides differences in evidence volume, missing outcomes and component tradeoffs. This project makes those differences inspectable without sending the encounter dataset to the browser. Ranking and comparisons stay within specialties; absent evidence is never silently turned into a zero score.

## Interactive analytics

- **Quality vs. cost:** all eligible providers in a selected specialty, default Cardiology. Hover/focus for score and raw mean cost; click/Enter opens the existing profile. Diamonds have strictly higher-than-mean scores and lower-than-mean costs. Dashed references are SQL cohort means, not clinical targets. An expandable table lists every point.
- **Component comparison:** grouped horizontal bars for outcome (60%), cost (25%), reliability (10%), volume (5%), on a fixed 0–100 scale. Exact component and weighted-point values accompany the existing detailed profiles. Up to three providers in one specialty remain supported.
- **Evidence:** specialty eligibility stacks with exclusive reasons, plus outcome-completeness bins. Fewer than 30 observed outcomes takes precedence over low completeness; missing materializations and no-encounter cases are explicit. Missing evidence does not mean low quality.

These charts use lightweight React SVG and semantic HTML rather than adding a chart package. Responsive sizing, text labels, keyboard actions, accessible tables, loading, error and empty states are explicit. Dense points may overlap; the table preserves access to every eligible provider. Real-browser visual verification is pending.

## Data processing and score methodology

The deterministic generator creates fictional providers and encounters. Validation precedes a transactionally replaced snapshot. PostgreSQL aggregates observed outcomes, raw mean cost, risk-adjusted outcome residuals and normalized cost ratios. Python calculates stored components and specialty ranks; API requests read these materialized results.

With observed outcomes `n`, total encounters `N`, residual `r = mean(outcome − (0.95 − 0.30 × risk))`, and normalized specialty cost ratio `c`:

- Shrinkage `w = n / (n + 50)`.
- Outcome `clamp(50 + 250 × r × w, 0, 100)`.
- Cost `clamp(50 + 50 × (1 − c) × w, 0, 100)`.
- Reliability `100 × (n/N) × w`; volume `100 × min(N/200, 1)`.
- Final score `0.60 × outcome + 0.25 × cost + 0.10 × reliability + 0.05 × volume`, rounded to two decimals, only when `n ≥ 30` and completeness `n/N ≥ 0.8`. Zero encounters is ineligible.

Costs are normalized per procedure and risk before comparison with the specialty mean. The scatter intentionally shows raw mean cost, so it is not the cost component. Higher simulated scores or lower costs do not establish actual clinical superiority. The scoring algorithm, generator and assumptions are unchanged in 2.0.

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

For the Make-based commands below: Python 3.9+ for the small setup script, Docker Desktop or Docker Engine with Compose v2 or newer, and Make. Git is needed only for cloning/version control; ZIP users can skip git clone. The application container itself uses Python 3.12. Windows users can run the commands in WSL2. No paid services or API keys are needed.

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

2.0 local checks: **28 backend passed / 14 PostgreSQL skipped; 13 frontend passed / 1 live skipped; production build, Ruff and Prettier passed.** Compose configuration parsed. Docker engine was unavailable; Playwright failed at Chrome launch before navigation (one failed, one not run). No actual upgraded screenshots or end-to-end pass are claimed. See [verification details and safe local steps](docs/VERIFICATION_2.0.md).


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

See the [historical 1.x verification report](docs/IMPLEMENTATION_VERIFICATION_REPORT.md), [historical benchmark](docs/benchmark.json), and test result logs. Docker and browser execution limitations are recorded, not represented as passing checks. GitHub Actions is configured to exercise Compose and Playwright on a normal runner; it has not run remotely yet.

## Screenshots

No 2.0 screenshots are included because Chrome aborted before navigation in this environment. [Capture instructions and exact filenames](docs/SCREENSHOTS_2.0.md) cover Overview, Analytics, Explorer, Profile, Comparison and two mobile layouts. Run Playwright locally and inspect the actual images before adding them to this README. No mockups are presented as screenshots.

## API examples

```bash
curl 'http://localhost:8000/api/providers?specialty=Cardiology&page=1&page_size=12'
curl 'http://localhost:8000/api/providers?q=Demo&min_quality=45&max_cost=700&sort=cost'
curl 'http://localhost:8000/api/providers/1'
curl 'http://localhost:8000/api/compare?ids=1&ids=6'
curl 'http://localhost:8000/api/analytics'
curl 'http://localhost:8000/api/analytics/quality-cost?specialty=Cardiology'
curl 'http://localhost:8000/api/analytics/evidence'
curl 'http://localhost:8000/api/pipeline'
```

Comparison accepts two or three distinct providers within one specialty. Bad parameters return 422, missing providers 404, and database failures 503. The API is deliberately read-only; pipeline execution requires CLI access.

The two new analytics endpoints use provider/score joins and SQL aggregates, never encounter payloads. Unknown specialties return an empty cohort with null means. Evidence uses a left join so providers missing scores remain counted. Responses are documented at `/docs`.

## Technical decisions

Synchronous SQLAlchemy keeps a small database-backed API easy to follow. PostgreSQL does set-based normalization and aggregation; Python owns deterministic generation and scoring. Scores are stored to keep reads cheap. Alembic owns schema evolution. Full replacement with a transaction is appropriate for this bounded demo; it is not a production claims ingestion strategy. Custom CSS and semantic HTML avoid an oversized UI framework. No dbt, Airflow, AWS, dlt or Kubernetes: one local pipeline does not justify their operational overhead.

## Documentation and learning

- [Beginner guide](docs/CareRank_Lab_Beginners_Guide.md) and [Mac setup](docs/MAC_SETUP_GUIDE.md)
- [Current Mac verification report](docs/MAC_VERIFICATION_REPORT.md)
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

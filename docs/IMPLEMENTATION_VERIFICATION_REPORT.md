# CareRank Lab Implementation Verification Report

Historical Linux build record. See [MAC_VERIFICATION_REPORT.md](MAC_VERIFICATION_REPORT.md) for the later Mac review and updated-code checks. The results below are retained as original evidence, not repeated Mac or Docker verification.

Verified November 14, 2026. The native application and database workflow are verified. The full final quality gate remains incomplete because Docker is unavailable and Chromium cannot launch in this environment. This package is ready for local review, not represented as production software.

## Results

| Requirement | Evidence and result |
|---|---|
| Backend dependencies | Exact requirements installed successfully with Python 3.12.14 |
| API startup and PostgreSQL | FastAPI served real requests against PostgreSQL 16.2 through the Vite proxy |
| Migrations | Alembic upgrade, downgrade and re-upgrade exercised in integration tests |
| Synthetic generation and pipeline | 1,000 fictional providers and 100,000 encounters generated, validated, loaded, aggregated and scored |
| Safe rerun and failure behavior | Integration tests verify replacement counts, rollback and failed audit records |
| Ranking and edge cases | pytest covers shrinkage, insufficient evidence, ties and invalid aggregates |
| Backend tests | 33 passed in 2.24 seconds; no skips; see backend-test-results.txt |
| Frontend and live integration | 5 passed including React → Vite → FastAPI → PostgreSQL; see live-ui-test-results.txt |
| Search and comparison | Live DOM workflow exercised specialty filtering, pagination, two-provider comparison, name search and profile |
| Production frontend | TypeScript check and Vite production build passed |
| Formatting | Ruff check and formatting passed for all 15 backend Python files; frontend Prettier check passed |
| Browser end-to-end | Attempted; Chromium aborted before test execution because Unix socket creation was denied. See e2e-test-results.txt |
| Screenshots and visual UI QA | Not available: browser could not launch. Screenshot capture is implemented in the Playwright workflow |
| Docker Compose startup | Not executed: Docker executable absent. Compose dependencies and health checks reviewed against official documentation |
| CI | GitHub Actions workflow supplied; not executed on GitHub |
| Documentation | Both Word guides rendered to page images; Markdown counterparts, exercises/solutions, security review and portfolio guide included |
| GitHub publication | No remote created and no push performed |

## Measured performance

The full default pipeline took **3.869 seconds**. After five warmups, 100 filtered Cardiology searches had a **1.772 ms median** and **2.475 ms p95**. The benchmark measures in-process SQLAlchemy count, page query and serialization, not HTTP latency, browser latency, concurrency or production capacity. Raw parameters and runtime versions are in benchmark.json. These values are observations from one environment, not expected service-level guarantees.

## Warnings and limitations

Pytest reported upstream AnyIO/pytest and Starlette/httpx deprecation warnings. Vite reported harmless-to-build lucide-react `use client` directive warnings. The npm process also reported an environment http-proxy configuration warning. No application test failed in the native test suite. Browser launch failure is an environment error and does not establish browser correctness.

The app intentionally lacks authentication and must remain local. Scores are synthetic educational heuristics with no clinical validation. The database account is shared by the read API and pipeline; use separate least-privilege roles for a production adaptation. No penetration test, vulnerability audit, clinical fairness assessment or load test was performed. Consult SECURITY_REVIEW.md.

## Remaining verification on a Docker-capable machine

1. Follow README prerequisites, then run `make up` from the repository root.
2. Open http://localhost:8080 and http://localhost:8000/docs.
3. In frontend/, run `npm ci`, `npx playwright install chromium`, then `BASE_URL=http://localhost:8080 npm run e2e`.
4. Inspect all five generated screenshots, check keyboard navigation and mobile layout, and add approved screenshots to README.
5. Run the provided CI workflow after publishing the repository. A successful local run does not establish CI success.

## Official references checked

- https://fastapi.tiangolo.com/tutorial/response-model/
- https://vite.dev/guide/
- https://docs.docker.com/compose/how-tos/startup-order/

Compatible dependency pins were checked by installation, test execution and a production TypeScript/Vite build. Container image pulls and a clean remote CI environment remain unverified.

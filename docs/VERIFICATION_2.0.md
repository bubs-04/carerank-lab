# CareRank Lab 2.0 verification — 2026-11-15

## Baseline and preservation

The uploaded `CareRank_Lab_Project(2).zip` contained 85 files. Byte comparison with the existing reviewed working repository found no differences before this upgrade. Work extended that repository. No new application was scaffolded. No Docker containers or database records were changed by this delivery, and nothing was published to GitHub.

Scoring, generator, pipeline, SQL event aggregation, database models/migrations, Compose, Dockerfiles, package dependencies/lockfile, and `frontend/src/api.ts` were preserved. The existing aborted-response guard and regression test remain.

## Executed checks

| Check | Result | What this proves / does not prove |
|---|---|---|
| Python scoring + portable analytics API/SQL suite | **28 passed** | Existing scoring tests plus 8 new tests execute actual SQL using isolated in-memory SQLite and FastAPI TestClient. Not PostgreSQL execution. |
| PostgreSQL integration suite | **14 skipped** | No disposable PostgreSQL test connection available. New cohort/evidence integration test is included. |
| Frontend Vitest / Testing Library | **13 passed, 1 skipped** | Includes 8 new analytics tests, existing UI checks and stale-response regression. The optional live server test is skipped without LIVE_URL. DOM tests do not verify actual browser layout. |
| TypeScript + Vite production build | **Passed** | Types compile and bundle builds. Existing lucide-react use-client bundler warnings remain; no server rendering is used. |
| Ruff lint and formatting | **Passed** | Backend source and tests conform. |
| Prettier frontend check | **Passed** | Source/config/E2E files conform. |
| Mac launcher regression tests | **3 passed** | Existing script behavior with stubbed Docker; not a container launch. |
| Compose configuration validation | **Passed** | `docker compose config --quiet` parses existing configuration. Does not start services. |
| Docker engine attempt | **Blocked** | `docker info` reported missing `/Users/.../.docker/run/docker.sock`. No available engine connection; full startup not attempted after that. |
| Playwright execution attempt | **Failed before navigation** | Chrome launched then exited SIGABRT; process cleanup reported EPERM. 1 failed, 1 did not run; no application assertion or screenshot completed. Stopped after the first failure. |
| Actual upgraded browser/mobile layout | **Unverified** | No screenshots were captured. Do not treat React DOM tests as visual browser verification. |
| Word document | **Structural validation only** | ZIP/XML, paragraphs/tables and embedded diagram checked. Word pagination/visual rendering was not available here. |

Raw logs are under `docs/verification/v2/`. Local absolute workspace paths and transient browser profile paths are redacted for publication. Earlier files under `docs/verification/`, the old Mac report, and the original benchmark describe earlier versions and are not evidence of a 2.0 live/browser pass. No new benchmark claim is made.

## New tests in detail

Portable API checks cover >100 eligible points, absence of pagination limits, SQL means, strict highlight flags, exclusion of unscored rows, specialty isolation, unknown/injection-like specialties, input length validation, exact 80% eligibility and just-below-80% completeness, precedence when both rules fail, missing materialization, zero encounters, 0% completeness, conserved totals, and empty database responses.

Frontend checks cover hover/focus information, Enter navigation, click navigation, table navigation, >100 SVG points, default specialty/filter requests, loading/error/empty states, evidence labels, component weights and contributions, unscored labeling, and application navigation. The existing delayed-response regression still passes.

PostgreSQL integration tests and real-browser workflows are implemented but remain pending execution in a supported environment. The browser suite captures Overview, Explorer, Profile, Comparison, Analytics, mobile Overview and mobile Analytics. It also checks horizontal overflow on mobile and keyboard navigation.

## Remaining issues before a live portfolio demonstration

1. Follow `UPGRADE_2.0_MAC.md` in your original folder to build and run API/web against your existing database. Keep `.env` and volumes.
2. Run the disposable PostgreSQL tests locally. SQLite tests exercise portable SQL logic but do not certify PostgreSQL driver behavior, isolation or query plans.
3. Run Playwright locally and inspect all screenshots, including labels, point interactions and mobile behavior. Dense scatter points can overlap; the complete table provides access to every provider. No visual layout approval is claimed.
4. Add actual screenshots to the README after capture. No placeholder images are disguised as results.
5. Open the Word walkthrough in Word or Pages and inspect page breaks. Its content/structure were checked, not rendered pagination.
6. Full-cohort point delivery is appropriate for this bounded demo (1,000 providers by default). Larger real systems would need a reviewed scale strategy, performance measurement and clinically governed methods.

## Publication review

The delivery ZIP excludes `.env`, credentials, `.git`, virtual environments, node_modules, build output, caches, browser traces, local database files and temporary artifacts. Existing `.env.example` is retained as a template. Source is synthetic; no real patient records are included. A heuristic secret scan is not a guarantee that no secret can exist; review any personal edits before publishing. Existing localhost bindings and API read-only behavior remain. No external publication, PR or deployment was performed.

# CareRank Lab Mac Review and Verification

Review date: November 14, 2026, America/New_York. This review used the supplied CareRank_Lab_Project.zip. The older incomplete Mac workspace was left untouched; changes were made to an extracted copy of the delivered repository. The application was not rewritten.

## What changed

- Fixed a reproduced response-order race in frontend/src/api.ts. An old response body could finish after a newer request and overwrite current React data. State updates now check the request's aborted signal. frontend/src/api.test.tsx failed before the fix and passed afterwards.
- Changed the GitHub Actions readiness check to the web proxy on port 8080. The previous check only waited for API port 8000, which did not establish web readiness. CI also uploads available browser screenshots and test traces as artifacts. This remote workflow has not run yet.
- Added a Mac launcher and read-only diagnostic script, with three launcher tests using a fake Docker command. The launcher creates a private .env without overwriting one that exists. These tests do not start Docker.
- Added the beginner's Word/Markdown guide, Mac installation/error guide and instructions for applying the fix to the already running copy. Corrected README setup prerequisites: the container's Python version is not a prerequisite for the shell launcher.
- No changes to the backend, database schema, scoring formula, dependency lockfile or Compose service definitions.

## Evidence from this review

| Check | Result and scope |
|---|---|
| Original app opens and provider comparison works | Reported by the user from their Mac. Manual check of the original running copy; no claim that the revised bundle is deployed. |
| Running site's HTTP health and endpoints | Passed 11 read-only HTTP requests through localhost:8080, including counts, search, filtering, sorting, pagination, profile, same-specialty comparison, validation errors and pipeline status. See verification/running-app-http.json. |
| Default data in running app | API reports 1,000 providers and 100,000 encounters, plus a successful pipeline audit. This is read-only evidence from the user's running service. |
| Backend pytest | 20 passed, 13 PostgreSQL integration tests skipped. Python 3.11.5 in a local test environment; production container remains Python 3.12. See verification/macos-backend.txt. |
| In-memory synthetic generation | Generated and validated 1,000 providers and 100,000 events; 2,533 missing outcomes. No database write in this check. See verification/macos-generation.json. |
| Frontend components and race regression | 5 passed, 1 live test skipped when no LIVE_URL was set. Node 24.15.0, locked dependencies. See verification/macos-frontend.txt. |
| Live React workflow | 6 tests passed with no skips. See verification/macos-live-frontend.txt for the run against the user's existing localhost:8080 service. It uses a simulated DOM, real HTTP, and the revised React source; it does not launch a real browser or replace the deployed frontend. |
| Frontend production build | TypeScript and Vite passed after the race fix. See verification/macos-build.txt. |
| Formatting | Ruff check/format passed for the 15 backend Python files; frontend Prettier check passed. See verification/macos-format.txt. |
| Launcher behavior | 3 passed: private credential creation/preservation, stop before writing if engine unavailable, stop before startup if configuration invalid. Fake Docker CLI, not real containers. |
| Compose structure | Real Docker Compose parsed config successfully and listed db, migrate, seed, api and web. No engine access required for this check. |
| Docker control from agent | Blocked: permission denied connecting to the Docker Desktop Unix socket. Not retried. This does not contradict the user's successful startup. |
| Separate native PostgreSQL | Initialization attempted once; blocked by shared-memory permission (shmget). No retry or bypass. |
| Real browser | One Chrome launch through Playwright attempted; process aborted before a page opened (SIGABRT/EPERM). No repeat of the blocked launch. |
| Included Playwright workflow | Discovered successfully with --list; execution not completed because browser launch was blocked. Discovery is not a passing end-to-end test. |
| Screenshots | None captured. The included workflow is configured to write all five requested views when run locally. Diagrams are labeled explanations, not screenshots. |
| Beginner guide | DOCX ZIP/XML integrity and embedded diagrams checked. A full page renderer was unavailable and Quick Look produced no usable preview. Full visual page QA remains unverified. Markdown contains the same instructional text. |

The initial Python test run crashed in the local readline/capture import. Disabling third-party plugin autoload and pytest capture allowed the unit suite to execute: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p no:capture -q`. This was a local runtime workaround, not an application change. Do not apply it routinely on a working Docker installation.

The Node initially on the Mac was 22.19.0, outside this project's declared runtime range. A workspace-only Node 24.15.0 executable was used for the checks; the user's global Node installation was not changed. npm ci succeeded and reported zero known vulnerabilities at installation time. This is not a comprehensive supply-chain audit. Vite reported lucide-react use-client directive warnings; the build completed. Backend tests reported the existing Starlette/httpx deprecation warning.

## Historical evidence retained

IMPLEMENTATION_VERIFICATION_REPORT.md, backend-test-results.txt, live-ui-test-results.txt and benchmark.json describe the earlier Linux build. Its recorded 33 backend passes, 5 frontend/live passes and pipeline/search timings were not rerun as full PostgreSQL or Docker benchmarks in this Mac review. They are retained rather than overwritten or relabeled. New logs are under docs/verification/; local workspace prefixes are normalized to <workspace> for portability.

## Publication review

Reviewed the application source, tests, migrations, SQL, frontend components/styles, Docker/Compose/Nginx configuration, CI, scripts, README and guides. Database access uses bound SQLAlchemy filters and fixed aggregation SQL. The API exposes read routes only. Compose binds published services to loopback and does not publish the database port. No real patient data is supplied. The displayed owner name is intentional portfolio information, not a login system.

A targeted text scan found no private-key blocks, GitHub token signatures, AWS access-key signatures or OpenAI-style secret signatures in the package candidates. This is not exhaustive secret detection. The locally generated .env is ignored and excluded. node_modules, dist, virtual environments, caches, database files, .git, browser traces and editor/system metadata are excluded from the final ZIP. Dependency manifests and lockfiles are included.

The README links to the current report, explicitly identifies missing screenshots and separates prior evidence from current checks. The original guides are retained; the new beginner guide explains this review's changes. No GitHub repository was created, no remote was configured, and no push or publication occurred.

## Remaining issues in plain English

1. The user's original website works manually and through the checked HTTP endpoints. The revised frontend still needs to be copied into that working folder and rebuilt; use APPLY_UPDATE.md.
2. A real browser must run the Playwright workflow on the user's Mac. The agent cannot confirm layout, keyboard accessibility or mobile appearance. Capture and inspect the five screenshots before using them in a public README.
3. Docker startup/rebuild for the updated source and the GitHub Actions run remain unverified by this agent. Existing successful user startup is recorded separately.
4. Full PostgreSQL integration tests should run against the disposable carerank_test database. Do not use the main demo database because tests drop/recreate tables.
5. The Word guide is structurally checked but its final rendered pagination needs inspection in Word. No claims of full visual QA are made.
6. The app remains a local educational demo: no authentication, no clinical validation, no uncertainty intervals, no production operations. It is unsuitable for real healthcare decisions or public production hosting as-is.

## Next action

Since the site already opens, begin with Lesson 3 in the beginner guide. Then follow APPLY_UPDATE.md to apply the small fix without replacing .env or the database. When ready, follow the Mac guide's Playwright instructions and keep the resulting screenshots and test output.

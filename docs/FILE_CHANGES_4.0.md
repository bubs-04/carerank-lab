# CareRank 4.0 file inventory

Baseline: `ce4daa4bbcc56324a9db76133075639c424f9a12` (merged PR #3). Security corrections update reviewed commit `db17958bc16211853a4c042aae0df46640ef2f4b` on existing PR #4.

The following is the complete source/configuration/documentation change list relative to the baseline. Captured verification artifacts are separated below.

| Status | Path |
|---|---|
| M | `.env.example` |
| M | `.github/workflows/ci.yml` |
| M | `README.md` |
| M | `backend/Dockerfile` |
| A | `backend/app/auth/__init__.py` |
| A | `backend/app/auth/__main__.py` |
| A | `backend/app/auth/api.py` |
| A | `backend/app/auth/config.py` |
| A | `backend/app/auth/dependencies.py` |
| A | `backend/app/auth/models.py` |
| A | `backend/app/auth/security.py` |
| A | `backend/app/auth/service.py` |
| A | `backend/app/auth/throttle.py` |
| A | `backend/app/bootstrap.py` |
| M | `backend/app/main.py` |
| M | `backend/app/monitoring/api.py` |
| M | `backend/app/monitoring/models.py` |
| M | `backend/app/monitoring/schemas.py` |
| M | `backend/app/monitoring/service.py` |
| A | `backend/app/runtime_role.py` |
| M | `backend/migrations/env.py` |
| A | `backend/migrations/versions/004_auth_operations.py` |
| A | `backend/migrations/versions/005_security_review.py` |
| A | `backend/tests/conftest.py` |
| M | `backend/tests/test_analytics.py` |
| M | `backend/tests/test_ingestion.py` |
| M | `backend/tests/test_integration.py` |
| M | `backend/tests/test_monitoring.py` |
| A | `backend/tests/test_runtime_role.py` |
| A | `backend/tests/test_security.py` |
| M | `compose.yaml` |
| A | `docs/ARCHITECTURE_4.0.md` |
| A | `docs/CHANGELOG_4.0.md` |
| A | `docs/DEMO_4.0_5_MINUTES.md` |
| A | `docs/FILE_CHANGES_4.0.md` |
| A | `docs/SECURITY_4.0.md` |
| A | `docs/SECURITY_REVIEW_4.0.md` |
| A | `docs/VERIFICATION_4.0.md` |
| A | `docs/architecture_4.0.svg` |
| A | `docs/runtime-grants.sql` |
| M | `frontend/Dockerfile` |
| A | `frontend/e2e/authenticated.ts` |
| M | `frontend/e2e/dataops.spec.ts` |
| M | `frontend/e2e/monitoring.spec.ts` |
| A | `frontend/e2e/security.spec.ts` |
| M | `frontend/e2e/workflow.spec.ts` |
| M | `frontend/nginx.conf` |
| A | `frontend/src/Administration.test.tsx` |
| A | `frontend/src/Administration.tsx` |
| A | `frontend/src/Auth.test.tsx` |
| A | `frontend/src/Auth.tsx` |
| M | `frontend/src/DataOps.tsx` |
| A | `frontend/src/IncidentActions.test.tsx` |
| A | `frontend/src/IncidentActions.tsx` |
| M | `frontend/src/Live.test.tsx` |
| M | `frontend/src/Monitoring.tsx` |
| M | `frontend/src/api.test.tsx` |
| M | `frontend/src/api.ts` |
| M | `frontend/src/main.tsx` |
| M | `frontend/src/styles.css` |
| M | `frontend/vite.config.ts` |
| M | `scripts/setup_env.py` |
| M | `scripts/start_mac.sh` |
| M | `scripts/tests/test_start_mac.py` |
| A | `scripts/verify_proxy_security.py` |

## Verification artifacts

Original 4.0 evidence remains under `docs/verification/v4.0/`. Security-correction evidence is under `docs/verification/v4.0-review/`:

- `docs/verification/v4.0-review/PREVIOUS_REPORT.md`
- `docs/verification/v4.0-review/administration-4.0.png`
- `docs/verification/v4.0-review/analyst-mobile-4.0.png`
- `docs/verification/v4.0-review/analyst-workspace-4.0.png`
- `docs/verification/v4.0-review/backend-final.txt`
- `docs/verification/v4.0-review/backend-format.txt`
- `docs/verification/v4.0-review/backend-lint.txt`
- `docs/verification/v4.0-review/build.txt`
- `docs/verification/v4.0-review/frontend-format.txt`
- `docs/verification/v4.0-review/frontend-live.txt`
- `docs/verification/v4.0-review/launcher.txt`
- `docs/verification/v4.0-review/main-before-005.json`
- `docs/verification/v4.0-review/migration-guard.txt`
- `docs/verification/v4.0-review/migration-rerun.txt`
- `docs/verification/v4.0-review/mobile-monitoring.png`
- `docs/verification/v4.0-review/monitoring.png`
- `docs/verification/v4.0-review/playwright.txt`
- `docs/verification/v4.0-review/preservation.txt`
- `docs/verification/v4.0-review/proxy.txt`
- `docs/verification/v4.0-review/sign-in-4.0.png`

No dependency manifest, applied migration 001–004, ranking formula, generator, CMS connector, validation policy or snapshot-comparison algorithm changed. The new migration is 005. Persistent cloud helper changes are outside this Git diff and are explained in VERIFICATION_4.0.md. Runtime data, credentials, dependency directories, build output and browser traces are excluded.

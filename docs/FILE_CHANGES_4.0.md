# CareRank 4.0 file inventory

Baseline: `ce4daa4bbcc56324a9db76133075639c424f9a12` (merged PR #3).

Source and configuration files below are the complete changes relative to that baseline. Verification artifacts are listed separately to distinguish captured evidence from application source.

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
| A | `backend/app/bootstrap.py` |
| M | `backend/app/main.py` |
| M | `backend/app/monitoring/api.py` |
| M | `backend/app/monitoring/models.py` |
| M | `backend/app/monitoring/schemas.py` |
| M | `backend/app/monitoring/service.py` |
| M | `backend/migrations/env.py` |
| A | `backend/migrations/versions/004_auth_operations.py` |
| A | `backend/tests/conftest.py` |
| M | `backend/tests/test_analytics.py` |
| M | `backend/tests/test_ingestion.py` |
| M | `backend/tests/test_integration.py` |
| M | `backend/tests/test_monitoring.py` |
| A | `backend/tests/test_security.py` |
| M | `compose.yaml` |
| A | `docs/ARCHITECTURE_4.0.md` |
| A | `docs/CHANGELOG_4.0.md` |
| A | `docs/DEMO_4.0_5_MINUTES.md` |
| A | `docs/SECURITY_4.0.md` |
| A | `docs/VERIFICATION_4.0.md` |
| A | `docs/architecture_4.0.svg` |
| A | `docs/runtime-grants.sql` |
| A | `frontend/e2e/authenticated.ts` |
| M | `frontend/e2e/dataops.spec.ts` |
| M | `frontend/e2e/monitoring.spec.ts` |
| A | `frontend/e2e/security.spec.ts` |
| M | `frontend/e2e/workflow.spec.ts` |
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
| A | `docs/FILE_CHANGES_4.0.md` |

## Verification artifacts

- `docs/verification/v4.0/administration-4.0.png`
- `docs/verification/v4.0/analyst-mobile-4.0.png`
- `docs/verification/v4.0/analyst-workspace-4.0.png`
- `docs/verification/v4.0/analytics.png`
- `docs/verification/v4.0/backend-format.txt`
- `docs/verification/v4.0/backend-lint.txt`
- `docs/verification/v4.0/backend.txt`
- `docs/verification/v4.0/before-content.json`
- `docs/verification/v4.0/build.txt`
- `docs/verification/v4.0/comparison.png`
- `docs/verification/v4.0/database-permissions.txt`
- `docs/verification/v4.0/dataops.png`
- `docs/verification/v4.0/explorer.png`
- `docs/verification/v4.0/final-preservation.txt`
- `docs/verification/v4.0/frontend-format.txt`
- `docs/verification/v4.0/frontend-live.txt`
- `docs/verification/v4.0/frontend.txt`
- `docs/verification/v4.0/launcher.txt`
- `docs/verification/v4.0/main-preservation.txt`
- `docs/verification/v4.0/mobile-analytics.png`
- `docs/verification/v4.0/mobile-dataops.png`
- `docs/verification/v4.0/mobile-monitoring.png`
- `docs/verification/v4.0/mobile.png`
- `docs/verification/v4.0/monitoring.png`
- `docs/verification/v4.0/overview.png`
- `docs/verification/v4.0/playwright.txt`
- `docs/verification/v4.0/provider-profile.png`
- `docs/verification/v4.0/sign-in-4.0.png`

No dependency manifest, prior migration, ranking formula, generator, CMS connector, validation policy or snapshot-comparison algorithm was changed. Persistent cloud installation/session scripts are outside this diff.

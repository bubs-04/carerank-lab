# Exact CareRank 3.0 file changes

Baseline: the delivered CareRank Lab 2.0 ZIP, not an authenticated GitHub commit. No files deleted. 7 existing files modified; 43 files added.

See CHANGELOG_3.0.md for the meaning of each change group. Existing scoring, generator, synthetic schema, Compose, Dockerfiles, dependencies, analytics and race guard remain unchanged.

| Change | Exact path |
|---|---|
| Modified | `.github/workflows/ci.yml` |
| Modified | `README.md` |
| Modified | `backend/app/main.py` |
| Modified | `backend/migrations/env.py` |
| Modified | `backend/tests/test_integration.py` |
| Modified | `frontend/src/App.tsx` |
| Modified | `frontend/src/styles.css` |
| Added | `backend/app/ingestion/__init__.py` |
| Added | `backend/app/ingestion/__main__.py` |
| Added | `backend/app/ingestion/api.py` |
| Added | `backend/app/ingestion/compare.py` |
| Added | `backend/app/ingestion/config.py` |
| Added | `backend/app/ingestion/connector.py` |
| Added | `backend/app/ingestion/models.py` |
| Added | `backend/app/ingestion/schemas.py` |
| Added | `backend/app/ingestion/service.py` |
| Added | `backend/app/ingestion/validation.py` |
| Added | `backend/migrations/versions/002_registry.py` |
| Added | `backend/tests/fixtures/cms_registry_a.csv` |
| Added | `backend/tests/fixtures/cms_registry_b.csv` |
| Added | `backend/tests/test_ingestion.py` |
| Added | `docs/API_3.0.md` |
| Added | `docs/CHANGELOG_3.0.md` |
| Added | `docs/CareRank_3.0_Data_Engineering_Guide.docx` |
| Added | `docs/CareRank_3.0_Data_Engineering_Guide.md` |
| Added | `docs/DEMO_3.0_2_MINUTES.md` |
| Added | `docs/EXERCISES_3.0.md` |
| Added | `docs/FILE_CHANGES_3.0.md` |
| Added | `docs/UPGRADE_3.0_MAC.md` |
| Added | `docs/VALIDATION_3.0.md` |
| Added | `docs/VERIFICATION_3.0.md` |
| Added | `docs/architecture_3.0.png` |
| Added | `docs/dataops-openapi.json` |
| Added | `docs/verification/v3/backend.txt` |
| Added | `docs/verification/v3/build.txt` |
| Added | `docs/verification/v3/docker.txt` |
| Added | `docs/verification/v3/fixture-cli.txt` |
| Added | `docs/verification/v3/format.txt` |
| Added | `docs/verification/v3/frontend.txt` |
| Added | `docs/verification/v3/launcher.txt` |
| Added | `docs/verification/v3/live-final-first.txt` |
| Added | `docs/verification/v3/live-final-rerun.txt` |
| Added | `docs/verification/v3/live-result.json` |
| Added | `docs/verification/v3/migration-live-sqlite.txt` |
| Added | `docs/verification/v3/playwright.txt` |
| Added | `docs/verification/v3/preservation.txt` |
| Added | `docs/verification/v3/ruff.txt` |
| Added | `frontend/e2e/dataops.spec.ts` |
| Added | `frontend/src/DataOps.test.tsx` |
| Added | `frontend/src/DataOps.tsx` |

# Upgrade CareRank 2.0 to 3.0 on your Mac

This release adds an isolated public registry. It does not change synthetic providers, encounters, scores, scoring rules, or Docker service definitions. Nothing has been pushed or deployed. Perform these steps in your existing repository, not a new project folder.

## 1. Confirm your branch and preserve work

Open Docker Desktop and wait for it to finish starting. Open Terminal, type `cd `, drag your existing `carerank-lab` folder from Finder into Terminal, and press Return.

```bash
pwd
git status --short
git branch --show-current
git remote -v
docker compose ps -a
```

Your remote should be your existing `bubs-04/carerank-lab` repository. Your branch should be `feat/cms-data-ingestion`. If needed, switch to that already-created branch:

```bash
git switch feat/cms-data-ingestion
```

If there are uncommitted personal changes, save/review them before applying the update. Do not reset or overwrite them. Record the current commit so you can return to it:

```bash
git rev-parse HEAD
```

The supplied patch was prepared against the exact 2.0 ZIP previously delivered in this conversation. Private GitHub authentication was unavailable; newer remote changes were not read. A patch conflict is a reason to reconcile your branch, not force an overwrite.

## 2. Back up your existing database and credentials

Start only your existing database container if it is stopped. If `ps -a` shows no existing containers, first locate your original Compose folder/project name; do not initialize another volume.

```bash
docker compose start db
docker compose exec -T db pg_isready -U carerank -d carerank
```

Wait for “accepting connections.” Then:

```bash
umask 077
mkdir -p ../carerank-private-backups
backup_stamp=$(date +%Y%m%d-%H%M%S)
backup_file="../carerank-private-backups/carerank-$backup_stamp.dump"
docker compose exec -T db pg_dump -U carerank -d carerank -Fc > "$backup_file"
test -s "$backup_file" && echo 'Nonempty backup created'
cp -p .env "../carerank-private-backups/env-$backup_stamp"
shasum -a 256 .env
docker compose exec -T db psql -U carerank -d carerank -c 'SELECT (SELECT count(*) FROM providers) AS providers, (SELECT count(*) FROM encounters) AS encounters, (SELECT count(*) FROM scores) AS scores;'
```

The dump must complete without an error. Verify its archive structure without restoring anything:

```bash
docker compose exec -T db pg_restore --list < "$backup_file"
```

You should see table/data archive entries. This is an archive inspection, not a full test restore. Keep the backup and `.env` copy private, outside Git. Record the counts/checksum for comparison after the upgrade.

## 3. Apply the exact changes

Download `CareRank_3.0_Changes.patch`. Set PATCH to the actual downloaded file; replace the example path. Do not copy `.git` from any extracted ZIP.

```bash
PATCH="$HOME/Downloads/CareRank_3.0_Changes.patch"
git apply --check "$PATCH"
```

No output and exit success means the patch applies cleanly. If it reports conflicts, stop here: provide a current ZIP of `feat/cms-data-ingestion` for reconciliation, or review the conflicting files individually. Do not use `git reset --hard`, `--reject` or overwrite the whole repository to bypass the conflict.

When the check succeeds:

```bash
git apply "$PATCH"
git diff --stat
git status --short
shasum -a 256 .env
```

The credential checksum must remain unchanged. The complete source ZIP is also supplied for inspection, but the patch is the safer way to upgrade a possibly newer Git checkout. Read `FILE_CHANGES_3.0.md` for the exact file list.

## 4. Build, migrate, and restart only API/web

```bash
docker compose config --quiet
docker compose build api web
docker compose run --rm --no-deps api alembic current
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps api alembic current
```

The final migration should show revision `002`. This migration adds six `registry_*` tables. It does not alter synthetic tables or run the synthetic generator. PostgreSQL migration execution was not available in the delivery environment; inspect any failure before proceeding.

```bash
docker compose up -d --no-deps api
curl -fsS http://localhost:8000/api/health
docker compose up -d --no-deps --force-recreate web
curl -fsS http://localhost:8080/api/dataops/status
open http://localhost:8080
```

Wait for API health to return `{"status":"ok"}` before restarting web. If it is not ready, inspect `docker compose logs --tail=80 api`. Recreating web refreshes Nginx's API address. Verify the synthetic counts from Step 2 again.

Do not use `make up`, `make rebuild`, the fresh-install launcher, or `make pipeline` for this upgrade: those paths may run the seed dependency. Never run `docker compose down -v` or delete Docker volumes to solve an upgrade error.

## 5. Verify the deterministic fixture first

These commands populate only the separate fixture registry, not the synthetic tables or live CMS source:

```bash
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_b.csv --max-rows 5
```

Each fixture has 5 rows: 4 valid, 1 rejected, and 3 optional-field warning findings. Open Data operations, choose Deterministic fixture, and click Refresh status. Select A as older and B as newer. Expected comparison: 1 added, 1 removed, 1 changed, 2 unchanged. One retained record changes both specialty and city. Inspect findings and records.

Rerun fixture B: the command should report `no_change` and the same snapshot ID. The UI calls this “Version reused.” That means an existing matching version was reused; it does not necessarily mean the content matches the immediately preceding retrieval.

## 6. Ingest real CMS public records

```bash
docker compose run --rm --no-deps api python -m app.ingestion --max-rows 1000
```

The command resolves CMS metadata, streams a bounded CSV prefix, validates it and commits a snapshot. No API key is needed. Switch Data Operations to Live CMS registry and refresh. Inspect the release, counts, source records, checksum and any findings.

A successful job exits 0. Failed jobs exit 1 and retain an audit when the database is available. Interrupts exit 130. An already-existing matching projection returns `no_change`; no duplicate version is created. The default row target is 1,000 and the hard maximum is 5,000. Fewer rows than requested is an incomplete batch and will not publish a snapshot.

For environment-based limits inside Docker, pass them explicitly; Compose does not automatically forward arbitrary entries from your local `.env`:

```bash
docker compose run --rm --no-deps -e CMS_MAX_ROWS=1000 -e CMS_TIMEOUT_SECONDS=20 -e CMS_ATTEMPTS=3 api python -m app.ingestion
```

Do not change the row target when you want comparable versions. Versions with different source modes, row limits or policy versions cannot be compared. Samples capture the first N source rows, not a representative national population. Membership changes can reflect movement at the sampling boundary.

## 7. Tests

Portable backend tests inside the API image:

```bash
docker compose run --rm --no-deps api pytest tests/test_scoring.py tests/test_analytics.py tests/test_ingestion.py -q
```

The optional live test is skipped by default. To explicitly enable it:

```bash
docker compose run --rm --no-deps -e CMS_LIVE_TEST=1 api pytest tests/test_ingestion.py -k live_cms_optional -q
```

For PostgreSQL integration tests, create a separate disposable database. Never use `carerank` as TEST_DATABASE_URL; the test fixture drops/recreates tables.

```bash
docker compose exec -T db createdb -U carerank carerank_test_v3
docker compose run --rm --no-deps api python -c 'import os,subprocess; from sqlalchemy.engine import make_url; u=make_url(os.environ["DATABASE_URL"]).set(database="carerank_test_v3"); os.environ["TEST_DATABASE_URL"]=u.render_as_string(hide_password=False); raise SystemExit(subprocess.call(["pytest","-q"]))'
```

If that test database already exists, choose another name in both commands. Do not drop an unknown database. The URL is derived inside the container without printing credentials.

With Node 24.15+ installed, frontend/browser tests run from your original repository:

```bash
cd frontend
npm ci
npm test
npm run build
npm run format:check
npx playwright install chromium
BASE_URL=http://localhost:8080 DATAOPS_E2E=1 npm run e2e
cd ..
```

Run both fixtures before enabling DATAOPS_E2E. The browser tests only read data; they never trigger ingestion. They capture actual screenshots if the browser can launch.

## Diagnostics and rollback considerations

| Symptom | Diagnostic command | Meaning / response |
|---|---|---|
| Docker cannot connect | `docker info` | Start Docker Desktop in normal Terminal. This delivery could not access its socket. |
| Registry endpoint returns 503 | `docker compose run --rm --no-deps api alembic current` | Check migration 002 exists; then inspect API logs. Do not reset data. |
| CMS job fails | `docker compose logs --tail=80 api` | One-off CLI output is the primary job log; API logs help with reads only. Inspect Data Operations → attempts/findings for the safe error code. |
| `cms_http_403` / transport failure | `curl -I https://data.cms.gov/provider-data/` | Network/proxy/source access issue. Stop repeated retries; the connector already bounds attempts. Do not disable TLS or spoof credentials. |
| `http_proxy_dependency_missing` | `docker compose run --rm --no-deps api python -c 'import socksio'` | Only relevant to a configured SOCKS proxy. Use an explicitly reviewed image dependency update for `httpx[socks]`; do not disable the proxy to bypass controls. |
| `schema_missing_or_colliding_columns` | `curl -fsS http://localhost:8080/api/dataops/status` | Review the current official dictionary and connector before retrying; no snapshot was accepted. |
| `incomplete_batch` / `byte_limit` | `curl -fsS http://localhost:8080/api/dataops/runs` | Requested prefix was not fully received or exceeded the byte limit. Check limits/source status; do not call it a complete national dataset. |
| `running` after a process crash | `docker compose ps -a` | Confirm the one-off ingestion worker has stopped. SIGKILL cannot finalize its audit. Only then use the explicit recovery command below. |
| Comparison rejected | `curl -i 'http://localhost:8080/api/dataops/compare?old_id=OLD&new_id=NEW'` | Replace OLD/NEW with actual IDs. HTTP 422 means source/scope/policy mismatch, 404 means missing version. |

Recovery after confirming a crashed worker is no longer running:

```bash
docker compose run --rm --no-deps api python -m app.ingestion --mark-interrupted ACTUAL_RUN_ID
```

Preferred rollback is **application-only**: return source to the prior reviewed commit, rebuild API/web and leave the additive registry tables intact. They do not affect 2.0 synthetic features. Use your recorded commit or a Git revert after reviewing changes; do not blindly discard uncommitted work.

Schema rollback is destructive to registry history. If you deliberately need it, stop ingestion workers and API/web, back up again, and run `docker compose run --rm --no-deps api alembic downgrade 001` **while the 3.0 image still contains revision 002**. It drops the six registry tables only. Then restore/rebuild the earlier application code and restart API/web. Do not downgrade to `base`, and do not drop the database volume. A full database restore replaces data and should be planned separately, preferably tested first in a disposable database.

## Review and commit, without pushing

```bash
git diff --check
git diff --stat
git diff -- backend/app/main.py backend/migrations/env.py frontend/src/App.tsx .github/workflows/ci.yml
git status --short
```

Review new files too (they do not appear in ordinary unstaged `git diff` until staged). Stage only the reviewed feature paths:

```bash
git add backend/app/ingestion backend/migrations/versions/002_registry.py backend/migrations/env.py backend/app/main.py backend/tests/test_ingestion.py backend/tests/test_integration.py backend/tests/fixtures frontend/src/DataOps.tsx frontend/src/DataOps.test.tsx frontend/src/App.tsx frontend/src/styles.css frontend/e2e/dataops.spec.ts .github/workflows/ci.yml README.md docs
git diff --cached --stat
git diff --cached --check
git status --short
git commit -m "Add versioned CMS registry ingestion and Data Operations"
```

Inspect staged `docs` carefully if you have unrelated personal changes. No `git push`, merge, visibility change or public deployment is included.

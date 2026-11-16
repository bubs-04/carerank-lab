# Upgrade your existing Mac installation from 3.0 to 3.1

Use your **existing** `carerank-lab` directory and its existing Compose project. This procedure does not replace `.env`, rerun the synthetic generator, or remove any Docker volume. The ZIP is a complete source copy for review; the patch is the recommended way to update your existing checkout. Do not drag the ZIP contents over your working folder.

The exact baseline is main commit `351d7143b49b3f2e151d6877d0074ef050d53a60`. PostgreSQL/Compose and browser execution were blocked in the delivery environment, so perform the checks below before considering the release locally verified. Stop at any failed command and inspect its error.

## 1. Open the correct folder and branch

Open Docker Desktop and wait until it says the engine is running. Open Terminal, type `cd `, drag your existing project folder into Terminal, then press Return. Run:

```bash
pwd
git status --short
git rev-parse HEAD
git branch --show-current
docker compose ps -a
```

`git status --short` should print nothing. Preserve any personal work before proceeding; do not reset it. HEAD must be the full baseline above. If the feature branch already exists at that baseline, use `git switch feat/data-quality-monitoring`. Otherwise create it:

```bash
git switch -c feat/data-quality-monitoring 351d714
```

If HEAD differs or the patch check later fails, reconcile those changes first. Do not force an overwrite. This delivery includes an exact-baseline patch, not a claim that it applies to every future commit.

`docker compose ps -a` must show your existing project containers. If it shows none, find the original folder/project name before continuing. A different directory or `-p` name can select a different volume and make your data appear missing. Do not create a replacement volume. If you previously used a custom project name, use that same `-p NAME` on every command below.

## 2. Back up data and credentials

Ensure no ingestion CLI is currently running. Start only the existing database service if it is stopped:

```bash
docker compose start db
docker compose exec -T db pg_isready -U carerank -d carerank
```

Wait for `accepting connections`. Create a private backup directory outside Git:

```bash
umask 077
mkdir -p ../carerank-private-backups
care_stamp=$(date +%Y%m%d-%H%M%S)
care_backup="../carerank-private-backups/carerank-before-3.1-$care_stamp.dump"
docker compose exec -T db pg_dump -U carerank -d carerank -Fc > "$care_backup"
test -s "$care_backup"
docker compose exec -T db pg_restore --list < "$care_backup"
cp -p .env "../carerank-private-backups/env-before-3.1-$care_stamp"
shasum -a 256 .env
```

`pg_dump` must finish successfully. A nonempty file alone is not enough: `pg_restore --list` should print database objects without errors. This inspects the archive; it is not a full restore test. Record the `.env` checksum privately. Do not commit the backup or credentials.

Record all preservation counts:

```bash
docker compose exec -T db psql -U carerank -d carerank -c 'SELECT (SELECT count(*) FROM providers) providers, (SELECT count(*) FROM encounters) encounters, (SELECT count(*) FROM scores) scores, (SELECT count(*) FROM registry_runs) registry_runs, (SELECT count(*) FROM registry_snapshots) snapshots, (SELECT count(*) FROM registry_records) registry_records, (SELECT count(*) FROM registry_changes) comparisons;'
```

For your stated installation, the first three counts should be 1,000 / 100,000 / 1,000. If they differ, record the actual values and investigate rather than reseeding. Registry counts depend on your ingestion history.

## 3. Check and apply the patch

Download `CareRank_3.1_Changes.patch`. If your browser changes its filename, use that exact filename below.

```bash
care_patch="$HOME/Downloads/CareRank_3.1_Changes.patch"
git apply --check "$care_patch"
git apply "$care_patch"
git diff --check
git diff --stat
git status --short
shasum -a 256 .env
```

No output from `git apply --check` means it can apply cleanly. If it reports a conflict, stop before applying; do not use `--reject`, `git reset --hard`, or copy an older repository over it. The credential checksum must match Step 2. New files appear in `git status` even before staging.

## 4. Build, migrate, and restart without reseeding

```bash
docker compose config --quiet
docker compose build api web
docker compose stop api web
docker compose run --rm --no-deps api alembic current
docker compose run --rm --no-deps api alembic upgrade 003
docker compose run --rm --no-deps api alembic current
```

Before migration, current should be 002. Afterward it should be 003. This migration adds `monitor_rules`, `monitor_evaluations`, `monitor_alerts`, `monitor_events` and an audit immutability trigger. It does not modify your existing ranking/registry tables or records. If migration fails, inspect the error before starting the new API. PostgreSQL applies the migration transactionally.

```bash
docker compose up -d --no-deps api
curl -fsS http://localhost:8000/api/health
docker compose up -d --no-deps --force-recreate web
curl -fsS 'http://localhost:8080/api/dataops/monitoring/summary?mode=cms'
open http://localhost:8080
```

Wait for `{"status":"ok"}` before starting web; if needed, inspect `docker compose logs --tail=80 api` and retry health after startup completes. Recreating web refreshes Nginx's API address. Repeat the preservation-count query from Step 2 now, before adding fixtures. All seven counts must be unchanged. Verify Overview, Explorer, a profile, same-specialty Comparison, Analytics and Data Operations.

**Do not use `make up`, `make rebuild`, `make pipeline`, or the fresh-install launcher for this upgrade.** Their dependency path can run seed. Never run `docker compose down -v`, Docker volume prune, or delete the volume as an upgrade remedy.

## 5. Evaluate existing registry history

```bash
docker compose run --rm --no-deps api python -m app.monitoring evaluate --mode cms --limit 100
docker compose run --rm --no-deps api python -m app.monitoring evaluate --mode fixture --limit 100
```

Repeat a mode's command if it evaluated 100 attempts; stop once it reports zero. This adds monitoring history only, with no external fetch and no new snapshots. In Data Operations, choose your source mode, open **Quality monitoring**, then **Refresh status**. A first compatible success can be partial because there is no baseline. A running/unevaluated attempt is pending. Zero alerts alone is not a pass.

For an offline demo, intentionally add two tiny fixture ingestions to the separate fixture source:

```bash
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5
docker compose run --rm --no-deps api python -m app.ingestion --fixture tests/fixtures/cms_registry_b.csv --max-rows 5
```

Each has four accepted rows, one rejected row and three warning findings. At default thresholds these create four warning alerts per attempt: rejection plus three missing-field rates. Five change rules are unavailable on the first comparable attempt; later comparison results depend on your fixture history. A repeated ingestion is a new attempt that reuses its snapshot; repeated evaluation of the same attempt does not duplicate its alerts.

## 6. Inspect and investigate locally

Copy one alert ID from its evidence panel. Replace the placeholder text:

```bash
docker compose run --rm --no-deps api python -m app.monitoring inspect ALERT_UUID
docker compose run --rm --no-deps api python -m app.monitoring investigate ALERT_UUID --actor 'Prabhat' --expected-revision 1 --status investigating --assign 'Prabhat' --note 'Checked the five-row fixture and confirmed the missing fields are intentional.'
```

Use the actual revision returned by inspect. Read the guide before resolving a real incident. Names are local operator labels; there are no authenticated accounts. Refresh the dashboard to see the decision and audit entry. A resolution closes an alert; it never changes the original evaluation or source data.

## 7. Run tests safely

Backend unit tests and frontend checks:

```bash
docker compose run --rm --no-deps api pytest -q
cd frontend
npm ci
npm test
npm run build
npm run format:check
cd ..
```

Host frontend commands require the repository's supported Node version (24.15+ within Node 24, or Node 26+). Check `node --version`. Backend PostgreSQL tests skip unless TEST_DATABASE_URL names an explicitly disposable database. **Those tests intentionally downgrade/drop tables and seed their test database. Never point them at `carerank`.** Create a fresh distinct test database:

```bash
docker compose exec -T db createdb -U carerank carerank_test_31
docker compose run --rm --no-deps api sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/carerank_test_31" pytest -q'
```

If that test database already exists, inspect it and choose a different unused name; do not drop an unknown database. Keep production DATABASE_URL unchanged. The command derives a test URL inside the container without printing the password.

After the fixture commands and with the app running:

```bash
cd frontend
npx playwright install chromium
BASE_URL=http://127.0.0.1:8080 DATAOPS_E2E=1 npm run e2e
cd ..
```

The suite verifies existing flows and monitoring, including Refresh status and mobile layout. Actual screenshots are written under docs only when browser tests reach those steps. Revisit **Quality monitoring** at a narrow window width and confirm navigation, filters, evidence and horizontal table scrolling remain usable.

## 8. Review and commit (no push)

```bash
git diff --check
git diff -- backend/app/ingestion/service.py compose.yaml frontend/src/DataOps.tsx
git add README.md .env.example .github/workflows/ci.yml backend compose.yaml frontend/src frontend/e2e docs
git diff --cached --stat
git diff --cached --check
git status --short
git commit -m "Add versioned data quality monitoring and local alert investigation"
```

Review the staged list before committing; it must not include `.env`, database dumps, node_modules or generated browser traces. This guide contains no push/merge/deploy command. Keep the commit hash for a later code rollback.

## Migration and rollback considerations

The safest code rollback leaves additive monitoring tables in place: stop API/web, return only the 3.1 code changes, rebuild, and restart API/web with `--no-deps`. The 3.0 code ignores those tables. Do not automatically downgrade just to roll back the interface.

If you specifically need to remove schema 003, first take a new full backup containing the monitoring investigation history. Stop all ingestion/monitoring workers and API/web. Using the 3.1 image, run:

```bash
docker compose run --rm --no-deps api alembic downgrade 002
```

This **deletes all monitoring rules, evaluations, alerts and audit events**. It retains registry history and synthetic data. The deleted monitoring history cannot be recovered by upgrading again; restore from backup if needed. Verify all seven preservation counts. Do not downgrade to 001 or base.

If the patch is still uncommitted and has no later overlapping edits:

```bash
git apply -R --check "$care_patch"
git apply -R "$care_patch"
```

If already committed, review and use `git revert YOUR_3_1_COMMIT` instead of rewriting history. Rebuild `api web` and repeat the no-dependency restart from Step 4. Avoid applying the reverse patch to unrelated personal edits.

To test backup restorability without overwriting the original database, create an unused database name and restore there:

```bash
docker compose exec -T db createdb -U carerank carerank_restore_check_31
docker compose exec -T db pg_restore -U carerank -d carerank_restore_check_31 < "$care_backup"
```

Check table counts there. This is a verification copy, not an instruction to replace your current database. A full production restore should be reviewed separately because it can undo all work since the backup.

## Diagnostic commands and meanings

| Symptom | Exact diagnostic | Meaning / next step |
|---|---|---|
| Docker command missing | `docker --version` | Install/open Docker Desktop if command is unavailable |
| Cannot connect to Docker | `docker info` | Engine stopped or socket access denied; start Desktop and inspect its status; do not delete volumes |
| No existing containers | `docker compose ls` then `docker compose ps -a` | Wrong folder/project name or stopped project; locate the original project |
| Database not ready | `docker compose exec -T db pg_isready -U carerank -d carerank` | Accepting connections is ready; otherwise inspect `docker compose logs --tail=80 db` |
| Missing migration/table | `docker compose run --rm --no-deps api alembic current` | Should be 003; apply additive migration after backup |
| API 503 or unavailable | `docker compose logs --tail=80 api` | Check migrations/connection; DQ configuration errors require finite allowed values |
| Web 502 after rebuild | `docker compose logs --tail=50 web` | Check API health, then recreate web with `--no-deps --force-recreate` |
| Port already used | `lsof -nP -iTCP:8000 -sTCP:LISTEN` and `lsof -nP -iTCP:8080 -sTCP:LISTEN` | Identify your existing process; do not stop unrelated work blindly |
| Pending monitoring | `curl -fsS 'http://localhost:8000/api/dataops/monitoring/summary?mode=cms'` | Running attempt or missing current profile; confirm worker status, then backfill terminal attempts |
| Old run stuck running | `docker compose ps -a` | Confirm the actual worker is stopped before `python -m app.ingestion --mark-interrupted RUN_UUID` |
| Stale investigation revision | `docker compose run --rm --no-deps api python -m app.monitoring inspect ALERT_UUID` | Another decision was saved; read it and use the new revision |
| Invalid transition | Same inspect command | Follow allowed lifecycle; open cannot go directly to resolved |
| Unexpected missing data | Preservation-count SQL from Step 2 | First check Compose project/volume identity; never seed to repair an unknown mismatch |
| Frontend dependency/build failure | `node --version` then `npm ci` inside frontend | Match engines in package.json; install locked dependencies |
| Browser missing | `npx playwright install chromium` inside frontend | Installs the matching browser; inspect actual launch errors if it still fails |
| Patch conflict | `git rev-parse HEAD` then `git apply --check "$care_patch"` | Confirm exact baseline and reconcile local edits instead of overwriting |

Logs can contain local paths and operator notes. Review them before sharing publicly. Do not paste `.env` contents or a full Compose configuration containing substituted credentials.

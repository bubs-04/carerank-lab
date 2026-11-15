# Upgrade your existing Mac installation to CareRank Lab 2.0

This update changes application code only. No schema migration, reseeding, or password change is required. Keep the original project folder and Compose project name so Docker keeps using your current database volume. Nothing has been published.

## 1. Open Docker and locate both folders

Open Docker Desktop from Applications and wait until its engine is running. Double-click `CareRank_Lab_2.0_Project.zip` in Finder to extract it into a separate folder. Do not drag it over your working project.

Open Terminal. Type `cd ` (including the space), drag your **original working carerank-lab folder** from Finder into Terminal, then press Return. Run:

```bash
pwd
ls compose.yaml
docker info
docker compose ps -a
```

`pwd` must show your original folder. `ps -a` should show your existing db, api and web containers (stopped is okay). If it shows no containers, locate the correct original folder or the custom Compose project name you used before. Do not launch a new database to solve a folder mismatch.

If `docker: command not found`, try this for the current Terminal session:

```bash
export PATH="$HOME/.docker/bin:$PATH"
docker version
```

If Docker reports a missing socket or cannot connect, finish starting Docker Desktop first. These are local Terminal commands; this delivery environment could not reach the engine.

## 2. Make a database backup and record counts

If the existing database container is stopped, start only that existing container:

```bash
docker compose start db
docker compose exec -T db pg_isready -U carerank -d carerank
```

Wait for “accepting connections.” Create a private backup directory outside the repository. Each backup uses a timestamp, so previous backups remain:

```bash
umask 077
mkdir -p ../carerank-backups
backup_file="../carerank-backups/carerank-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U carerank -d carerank -Fc > "$backup_file"
test -s "$backup_file" && echo 'Backup file is nonempty'
docker compose exec -T db psql -U carerank -d carerank -c 'SELECT (SELECT count(*) FROM providers) AS providers, (SELECT count(*) FROM encounters) AS encounters;'
shasum -a 256 .env
```

The dump command must finish without an error. Keep the counts and `.env` checksum in your Terminal window; they should be unchanged after the update. A nonempty file alone does not prove a restorable backup; `pg_restore --list` can inspect it if you have PostgreSQL utilities installed. Do not share your `.env` contents or dump publicly.

## 3. Copy the update while preserving local files

Remain in the **original folder**. Set `UPDATE` to the extracted update's `carerank-lab` folder. Replace the example path below with its actual path; Finder → select folder → Option-Command-C copies a pathname. Keep the quotes if your path has spaces.

```bash
UPDATE="/Users/YOUR_NAME/Downloads/CareRank_Lab_2.0_Project/carerank-lab"
test -f "$UPDATE/backend/app/analytics.py" && echo 'Update source found'
```

If that message is absent, correct the path. Some unzip tools extract `carerank-lab` directly in Downloads. Preview the copy:

```bash
rsync -avn --exclude='.env' --exclude='.env.*' --exclude='.git/' --exclude='node_modules/' --exclude='.venv/' --exclude='dist/' --exclude='pgdata/' "$UPDATE/" ./
```

Check that `.env` is not listed and that the destination is your original project. Then run the same command without `n`:

```bash
rsync -av --exclude='.env' --exclude='.env.*' --exclude='.git/' --exclude='node_modules/' --exclude='.venv/' --exclude='dist/' --exclude='pgdata/' "$UPDATE/" ./
shasum -a 256 .env
```

No `--delete` is used. This preserves local credentials, Git history, dependencies and unrelated files. It replaces project source files with the updated versions; save any personal code edits first. The checksum should match Step 2.

## 4. Build and replace only the API and website

```bash
docker compose config --quiet
docker compose build api web
docker compose up -d --no-deps api
curl -fsS http://localhost:8000/api/health
```

If curl initially fails, wait a few seconds and retry once. It must return `{"status":"ok"}` before the next step. If it continues failing, use the diagnostics below. Then:

```bash
docker compose up -d --no-deps --force-recreate web
curl -fsS http://localhost:8080/api/health
curl -fsS 'http://localhost:8080/api/analytics/quality-cost?specialty=Cardiology'
curl -fsS http://localhost:8080/api/analytics/evidence
open http://localhost:8080
```

Recreating web refreshes Nginx's API hostname resolution after the API container changes. `--no-deps` prevents the migration and seed services from running. Do not use `make up`, `make rebuild`, `make pipeline`, `docker compose down -v`, or `docker volume rm` for this upgrade. The initial-launch path intentionally seeds data; this upgrade path does not.

Verify unchanged database counts using the SQL command from Step 2. Open Analytics, change the specialty, hover/focus a point and open its profile. In Provider Explorer, filter to Cardiology, select two or three providers, and Compare. Confirm the component chart and existing breakdown both appear. A hard refresh (Command-Shift-R) replaces a stale browser page.

## Diagnostics

| Symptom | Exact command | Meaning and safe response |
|---|---|---|
| No containers listed | `docker compose ls` | Find the existing project; use its original directory/project name. Do not create another volume. |
| Build error | `docker compose build api web` | Read the first error. Package download failures require a working internet connection; compiler errors need investigation. Do not delete volumes. |
| API not healthy | `docker compose logs --tail=80 api` | Connection/authentication errors usually mean the original `.env` is missing or changed. Restore the original credentials. |
| Database unavailable | `docker compose logs --tail=80 db` | Look for readiness or startup errors; do not reset the volume as a first step. |
| New endpoint returns 404 | `curl -i http://localhost:8000/api/analytics/evidence` | Usually an old API image/container. Repeat the API build and `up --no-deps api`. |
| Web gives 502, direct API works | `docker compose logs --tail=80 web` | Recreate web after API is healthy using the command above. |
| Port already allocated | `lsof -nP -iTCP:8080 -sTCP:LISTEN` | Identifies the process on the web port. Check for a second Compose project; do not kill unrelated processes blindly. |
| Charts are empty | `curl -fsS http://localhost:8080/api/analytics/evidence` | Zero providers means an empty database. Nonzero exclusions may correctly explain an empty eligible cohort. Check project identity before running any pipeline. |
| Only some points highlighted | `curl -fsS 'http://localhost:8080/api/analytics/quality-cost?specialty=Cardiology'` | Strict above-mean score AND below-mean cost are required. Equal-to-mean values are not highlighted. |

## Tests and screenshots after the upgrade

Node 24.15+ is needed only for host-side frontend development/tests; Docker launches do not need host Node or Python. Use the earlier Mac setup guide for prerequisites.

From the original project root:

```bash
cd frontend
node --version
npm ci
npm test
npm run build
npm run format:check
LIVE_URL=http://localhost:8080 npm test
npx playwright install chromium
BASE_URL=http://localhost:8080 npm run e2e
cd ..
```

The last command runs real-browser workflows and captures seven PNG files in `docs/`. See `SCREENSHOTS_2.0.md`. Inspect the screenshots before publishing. Tests use your existing demo data read-only and expect default specialties and more than 12 eligible Cardiology providers; customized sparse data may not satisfy that fixture assumption.

Backend unit/portable SQL checks inside the built API image:

```bash
docker compose run --rm --no-deps api pytest tests/test_scoring.py tests/test_analytics.py -q
```

PostgreSQL integration tests require a **separate disposable database**. They drop/recreate its schema. Never point `TEST_DATABASE_URL` at `carerank`. Create and use a new database with a unique name (if the name already exists, choose another rather than deleting it):

```bash
docker compose exec -T db createdb -U carerank carerank_test_v2
# Derive the test URL inside the container, without printing credentials:
docker compose run --rm --no-deps api python -c 'import os,subprocess; from sqlalchemy.engine import make_url; u=make_url(os.environ["DATABASE_URL"]).set(database="carerank_test_v2"); os.environ["TEST_DATABASE_URL"]=u.render_as_string(hide_password=False); raise SystemExit(subprocess.call(["pytest","-q"]))'
```

No test commands above drop your main database. The disposable test database can be retained until you are comfortable removing it. Remote CI is configured but has not been run or published by this delivery.

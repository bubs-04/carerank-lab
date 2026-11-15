# CareRank Lab Mac Setup Guide

Your goal is to see a website at **http://localhost:8080**. `localhost` means your own Mac. The ZIP contains the ingredients for that website; double-clicking a source file does not start it. Keep this guide open beside Terminal and complete one numbered step at a time.

## 1 Install only what you need for the first launch

Open Apple menu → About This Mac. If it lists an Apple M-series chip, use the Apple silicon installer for Docker Desktop. If it lists Intel, use the Intel installer. Use the official page: https://docs.docker.com/desktop/setup/install/mac-install/.

Open the downloaded Docker disk image, drag Docker to Applications, and open Docker from Applications. Complete its setup prompts and wait for the engine to be running. Docker runs the project's Python, Node build tools, and PostgreSQL in containers: you do **not** need to install them separately just to launch this version. Docker Desktop was already present on the Mac inspected during this review; do not reinstall it merely because this agent could not access its socket.

Open Terminal using Spotlight (Command-Space, type Terminal, press Return). Paste one command at a time and press Return. Do not type the surrounding Markdown backticks.

```bash
docker version
docker compose version
```

The first command should show both Client and Server sections. Client alone is not enough. The second should print a Compose version. If Terminal says command not found, try this for the current Terminal window, then rerun the two checks:

```bash
export PATH="$HOME/.docker/bin:$PATH"
```

The launcher also checks Docker's usual per-user location. This is a PATH issue, not a reason to reinstall everything. Docker may require you to approve its ordinary macOS setup prompts yourself. Never fix socket errors by granting world-write permissions to the socket.

## 2 Unzip and enter the right folder

Download the updated project ZIP. In Finder, double-click it. Open the extracted folders until you find `carerank-lab`; inside it you must see README.md, compose.yaml, backend, frontend and scripts. Keep the entire folder together. Do not use the older incomplete workspace copy.

In Terminal type `cd ` with one space after cd, drag the **carerank-lab folder** from Finder into Terminal, and press Return. Dragging inserts the correct path even if it contains spaces. Then run:

```bash
pwd
ls
```

`pwd` prints the folder Terminal is using. `ls` lists its contents. If you do not see `compose.yaml`, you are in the wrong folder. Repeat the drag-and-drop step with the folder containing that file.

## 3 Launch

From that folder run:

```bash
bash scripts/start_mac.sh
```

This small launcher checks Docker, creates a random local password in a private `.env` file if none exists, validates Compose syntax, and runs `docker compose up --build -d`. It preserves an existing `.env`. Do not copy `.env.example` to `.env`: the launcher generates the real value. Never post your `.env` contents online.

The first launch downloads images and packages and may take several minutes. Keep Docker Desktop running. `-d` means services continue in the background after the command finishes. If it fails, use the diagnostics below; an error message is useful evidence, not a reason to delete the project.

Alternative for people who already have Python and Make: `make up`. This calls the original Python credential setup and the same Compose startup. The shell launcher is the beginner path and does not require Python or Make on the host.

## 4 Confirm every service

```bash
docker compose ps -a
```

Use the SERVICE column; generated container names may have a prefix.

| Service | What it does | Expected state after startup |
|---|---|---|
| db | Stores synthetic records | Up, healthy |
| migrate | Creates database tables | Exited (0) is success |
| seed | Generates and processes demo data | Exited (0) is success |
| api | Answers dashboard requests | Up, healthy |
| web | Serves the browser interface | Up/running; no web healthcheck is defined |

`migrate` and `seed` are one-time jobs, so Exited (0) is normal. Exited (1) or another nonzero code is a failure. A service that is Created or waiting may be blocked by an earlier step. The intended order is db → migrate → seed → api → web.

Check the API directly, then through the same web proxy the browser uses:

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8080/api/health
```

Both should return `{"status":"ok"}`. That proves connectivity, not that data loaded. Check the actual stored counts:

```bash
docker compose exec -T db psql -U carerank -d carerank -c 'SELECT (SELECT count(*) FROM providers) AS providers, (SELECT count(*) FROM encounters) AS encounters, (SELECT count(*) FROM scores) AS scores;'
```

The default dataset should show 1000, 100000 and 1000. Every provider has a score record, but some quality values are empty because evidence is insufficient. View the most recent pipeline attempts:

```bash
docker compose exec -T db psql -U carerank -d carerank -c 'SELECT status, providers, encounters, seconds FROM pipeline_runs ORDER BY started_at DESC LIMIT 3;'
```

The latest successful initial run should say success. Timing will vary. `bash scripts/check_local.sh` runs these diagnostic checks together; it stops on the first failing command.

## 5 Open and explore

```bash
open http://localhost:8080
```

In the browser, confirm Overview shows 1,000 providers and 100,000 encounters. Choose Explore providers, set Specialty to Cardiology, select two checkboxes, then choose Compare (2). Return to providers and click a provider name to see its profile. The Beginner's Guide explains these controls.

Interactive API documentation is at http://localhost:8000/docs. It is a technical testing page, not the dashboard. Port 5173 is only for the optional Vite development mode; Compose serves the website at 8080.

## 6 Stop and return later

From the same project folder:

```bash
docker compose stop
```

This pauses the containers and keeps your data. To resume the same containers:

```bash
docker compose start
open http://localhost:8080
```

If you used `docker compose down` instead, the containers were removed but the named data volume remains. Run the launcher again to recreate them. Startup may run the seed job again, replacing the fictional dataset. Do not use `docker compose down -v` casually: `-v` deletes the saved database volume.

To deliberately regenerate the default fictional dataset after startup:

```bash
docker compose run --rm --no-deps seed python -m app.pipeline
```

Use this only with the demo database running and already migrated. It replaces demo records and appends an audit entry. Refresh the browser afterwards; the page does not poll automatically.

## 7 Diagnose a problem without guessing

Run these from the folder with compose.yaml. Do not paste raw `.env` or full `docker compose config` output into a public issue; those can reveal credentials. `config --quiet` checks syntax without printing secrets.

| Symptom | Exact diagnostic command | Meaning and next action |
|---|---|---|
| docker: command not found | `ls "$HOME/.docker/bin/docker"` | If present, add that directory to PATH as in step 1. Otherwise finish Docker Desktop installation. |
| Cannot connect to daemon | `docker version` | Missing Server section means Terminal cannot reach the engine. Open Docker Desktop and wait; then check again. |
| Permission denied on socket | `docker context ls` | Check which context is active and use Docker Desktop's normal setup. If your own Terminal works but ChatGPT fails, the agent is restricted; run startup yourself. Do not chmod the socket. |
| No configuration file provided | `pwd` and then `ls compose.yaml` | Terminal is in the wrong folder. Drag the correct folder after cd. |
| Missing POSTGRES_PASSWORD | `test -s .env && echo 'Configuration file exists'` | If missing, rerun the launcher. If present, use the next syntax check; do not publish the file. |
| Compose validation error | `docker compose config --quiet` | The error names the invalid field or missing variable. Compare your file to the supplied version. |
| Image pull or package download failure | `docker compose build --progress plain` | Read the first actual error: DNS, timeout, registry credentials or package incompatibility. Check internet/VPN and Docker Desktop network settings before retrying. |
| Port already allocated | `lsof -nP -iTCP:8080 -sTCP:LISTEN` | Shows the process using 8080. For an API conflict repeat with 8000. Stop only the app you recognize, or change the host-side Compose port and the URL. Do not kill an unfamiliar process. |
| db unhealthy | `docker compose logs --tail=80 db` | Look for startup, disk or password errors. Do not delete the volume as your first response. |
| migrate exited nonzero | `docker compose logs --tail=80 migrate` | Usually connection or schema error; read the last error and check db first. |
| seed exited nonzero | `docker compose logs --tail=80 seed` | Data validation, loading or scoring failed. Check migrate and db; preserve the error before retrying. |
| API unhealthy or 503 | `docker compose logs --tail=80 api` | Check connection/migrations. A 503 is the API's safe database error, not a provider score. |
| Website returns 502 | `docker compose logs --tail=80 web api` | Web is up but cannot reach API. Check api health. After recreating api, `docker compose restart web` refreshes Nginx's upstream resolution. |
| Website connection refused | `docker compose ps -a` | Confirm web is running, correct port is used, and prior jobs succeeded. |
| Database password authentication failed | `docker compose logs --tail=80 db api` | An existing database volume keeps the password from its first initialization. Restore the matching local .env; changing it alone does not change the DB password. |
| Empty provider list | `curl -fsS http://localhost:8080/api/analytics` | Zero providers means no loaded dataset; inspect seed. Nonzero providers suggest overly restrictive UI filters; clear those fields. |
| Changes not visible | `docker compose build web` | Compose serves built files, not live source. Then `docker compose up -d --no-deps web` and reload the page. |
| Browser says Request failed (422) | `curl -i 'http://localhost:8080/api/providers?min_quality=50'` | API rejects invalid filter inputs. Use score 0–100 and positive cost. If this valid request works, inspect your UI input. |
| Disk space error | `docker system df` | Shows Docker storage usage. Inspect Docker Desktop storage; do not run broad prune commands without understanding what they delete. |
| Node EBADENGINE | `node --version` | For optional frontend tests use Node 24.15+ in the 24.x line or Node 26+. Node 22.19 on the inspected Mac is too old for this project's declared setup. Compose builds with its own Node image. |
| Playwright executable missing | `npx playwright --version` | From frontend/, install the locked packages with npm ci, then `npx playwright install chromium`. Do not initialize a second Playwright project. |
| npm ci fails or package missing | `npm --version` | Check Node version, internet and the lockfile. Run from frontend/. Do not delete package-lock.json to hide a dependency error. |
| Test skipped | Read the test summary | A skipped test did not pass. PostgreSQL tests need TEST_DATABASE_URL; the live DOM workflow needs LIVE_URL and a running app. |

If you ask for help, share the failing command, its error, `docker compose ps -a`, and the relevant last log lines after checking them for secrets. Your `.env` is not needed.

## 8 Run tests and capture screenshots after the website works

For browser tests install Node from https://nodejs.org/en/download using a version matching the project (24.x at least 24.15.0, or 26+). This is optional for the first Docker launch. In a new Terminal enter the same project root, then:

```bash
cd frontend
node --version
npm ci
npm test
npm run build
npx playwright install chromium
BASE_URL=http://localhost:8080 npm run e2e
```

The default component run skips the live DOM test. To exercise that additional workflow against the default 100,000-encounter dataset:

```bash
LIVE_URL=http://localhost:8080 npm test
```

A successful Playwright run writes these files under the root docs folder: overview.png, explorer.png, provider-profile.png, comparison.png and mobile.png. It also checks navigation, pagination, comparison, profile display and mobile horizontal overflow. Inspect screenshots yourself; a test passing does not prove every pixel or keyboard interaction is correct. No screenshots were captured by the restricted agent session.

To run the pure backend tests inside the existing API container, return to the project root:

```bash
cd ..
docker compose exec -T api python -m pytest tests/test_scoring.py -q
```

For full PostgreSQL integration, create a separate disposable test database once. Do not point these tests at the main demo database: they drop/recreate tables.

```bash
docker compose exec -T db createdb -U carerank carerank_test
docker compose exec -T api python -c 'import os, subprocess; from sqlalchemy.engine import make_url; os.environ["TEST_DATABASE_URL"] = make_url(os.environ["DATABASE_URL"]).set(database="carerank_test").render_as_string(hide_password=False); raise SystemExit(subprocess.call(["python", "-m", "pytest", "-q"]))'
```

If createdb says the test database already exists, reuse it only if it is the disposable test database you created. The second command keeps the password inside the container; it does not print it. A simpler supported alternative is the CI workflow, which creates its own disposable test database. The original Linux run passed 33 tests; this Mac review could run only the 20 database-independent tests.

## 9 Make one change

Open frontend/src/App.tsx in a code editor. Change only the Overview paragraph beginning “A clearer view of quality” to “My first CareRank Lab change.” Save. From the project root:

```bash
docker compose build web
docker compose up -d --no-deps web
open http://localhost:8080
```

Reload the browser and look below the Overview headline. This changes text, not the scoring algorithm. Restore the original sentence when finished. Run the frontend tests and production build from step 8. The headline itself is used by tests, so leave it unchanged for this first exercise.

For faster editing later, keep the Docker API running on 8000, run `npm run dev` from frontend/, and open http://localhost:5173. Vite reloads frontend changes automatically. Stop Vite with Control-C. Docker's page on 8080 does not auto-rebuild when you save a file.

## Official references

Docker Mac installation: https://docs.docker.com/desktop/setup/install/mac-install/
Compose readiness: https://docs.docker.com/compose/how-tos/startup-order/
Playwright setup: https://playwright.dev/docs/intro

These commands were reviewed and the available static/local checks were run. Complete Docker startup and browser execution still require your normal Mac Terminal outside the agent's restrictions. See MAC_VERIFICATION_REPORT.md for exact evidence.

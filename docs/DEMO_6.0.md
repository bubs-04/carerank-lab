# Garner engineering demonstration

CareRank is an independent portfolio project, not a Garner product. No patient data or clinical ranking claims. Current blocker: this environment denies `data.cms.gov`; genuine public CMS archive capture is not completed. The script below calls that out explicitly instead of presenting artificial records as public data.

## Prepare and reset

Install Docker/Compose v2 and Python 3.10+. From the repository root run `python3 scripts/demo.py start`, then open **http://127.0.0.1:8086**. The dedicated `carerank_demo` database has 1,000 synthetic providers, 100,000 synthetic encounters, 1,000 synthetic scores, two fixture versions, monitoring evidence and a disabled recovery pipeline. Three random development accounts are stored only in `.demo/accounts.json`; never record that file or passwords. The application containers use separate owner/API/worker credentials. After images are built, fixture workflows need no internet access.

For a real public CMS segment, first capture and review the bounded archive using [demo/README.md](../demo/README.md). Replay retains official provenance and the original capture date; it is not a fresh live retrieval. Restart the prepare service with the normal launcher after adding the archive. If it is unavailable, state the blocker and show fixture ingestion as a separate fallback; do not claim that acceptance item passed.

Before recording, use the Administrator to enable the seeded **Garner demo · deterministic recovery** schedule. Its first attempt fails with `demo_transient_failure`, waits five seconds, then retries successfully; the worker schedules it immediately on enable. Disable it after the successful run to avoid later scheduled executions during recording. Existing executions preserve their frozen policy.

After the first successful build, use `python3 scripts/demo.py start --no-build` for offline starts. In this managed cloud, builds required the session CA as a temporary BuildKit secret; repository Dockerfiles and TLS verification were preserved. That environment-specific trust setup is not needed on a standard trusted Docker network.

Reset only the dedicated demo:

```bash
python3 scripts/demo.py reset --confirm-reset carerank-demo-v6
python3 scripts/demo.py start
```

The reset verifies volume name and Compose/project labels, deletes only `carerank-demo-v6-pgdata`, and retains private local credentials. It must not be pointed at a main/test/production project. `stop` preserves the volume; repeated `start` preserves existing snapshots/accounts/history. Back up any demo evidence you want to keep before resetting. Do not run `app.pipeline` manually on retained data.

## 60-second introduction

“CareRank is my healthcare data engineering portfolio platform. It separates fictional provider scores from public CMS registry records and labeled test fixtures. I built the operational path around PostgreSQL: versioned ingestion, explainable quality rules, authenticated investigations, and durable scheduled jobs. Administrators configure schedules; Analysts investigate and operate jobs; Viewers inspect evidence. Authorization and CSRF checks happen on the backend. When a worker or database fails, a lease and publication checkpoint let another attempt recover without publishing duplicate content. We retain the failed attempt and decision history. I’ll demonstrate a scheduled transient failure and recovery, then inspect the reliability dashboard and measured restore evidence. This is an at-least-once design with idempotent publication, not exactly once. The AWS files are a reviewed deployment reference, not a claimed production deployment. This environment cannot fetch CMS, so I’ll clearly label the fixture fallback.”

## Six-minute script and shot plan

| Time | Screen/action | Engineering point and visible evidence |
|---|---|---|
| 0:00–0:45 | Login as Viewer; Overview, then Data operations | Do not film credentials. Fictional scores stay separate from registry identities; Viewer has no write controls. Mention backend 403/CSRF negative tests. |
| 0:45–1:30 | Data operations → source/version → run provenance | With a reviewed CMS archive, show official dataset URL, capture time and **Archived public CMS data**. Without it, visibly select Fixture and state the CMS network blocker. Never call this a live national dataset. |
| 1:30–2:10 | Compare fixture versions A and B; inspect validation/quality findings | Added/removed/changed membership in bounded snapshots is not proof of real-world provider departures. Explain hashes, row validation and source scope. |
| 2:10–3:00 | Logout, login as Analyst; acknowledge, assign to self, investigate, resolve an open alert with a decision | Show timeline identity/time/prior/new state and resolution. Reopen with a reason if useful. Concurrent edits use revisions and return a conflict instead of overwriting. |
| 3:00–4:20 | Login as Administrator; Pipeline operations → seeded schedule → enable → inspect execution | Capture `scheduled` trigger, first failed attempt, five-second backoff, second success and events. Inspect linked snapshot and alerts. Disable schedule after the run. The transient failure is development-only and deterministic. |
| 4:20–5:15 | Reliability → 24-hour view → pipeline history | Show real success denominator, retry count, duration, current queue and worker pulse; no invented uptime percentage. Explain 30-second staleness and bounded windows. |
| 5:15–6:00 | Architecture document and `RELIABILITY_6.0.json` | Show 24 restored table fingerprints, worker recovery and database crash evidence, and local query measurements. Explain single-host/AWS verification limits and next production gates. |

Record at 1440×1000, 100% zoom; show one short 390px mobile shot of Reliability. Keep cuts between authentication sessions, not between a failure and its recovery evidence. Avoid filming account files, environment variables, tokens, DevTools cookies or database URLs. Screenshot evidence is generated by the real Playwright workflow at [reliability-6.0.png](reliability-6.0.png); no mockups are substituted for captures.

## Ten grounded engineering interview questions

1. **Why PostgreSQL instead of another queue?** The workload already needs transactional snapshots/audit. Row locks, unique constraints and bounded polling provide a small inspectable system. Dedicated queues become relevant with demonstrated throughput or isolation requirements.
2. **What delivery guarantee do you provide?** At least once. Retries may fetch twice; a fenced transaction and content/checkpoint identity prevent duplicate publication. External irreversible effects would need their own idempotency protocol.
3. **What if the worker dies after publishing?** The durable published-run checkpoint lets recovery evaluate monitoring without another publication. Interrupted attempts and retry scheduling remain in history.
4. **How do you fence a stale worker?** Publication validates the current claim/lease while holding the execution row lock. The supervisor stops work after its last confirmed lease; a stale child cannot publish as the new attempt.
5. **How are investigation races handled?** Backend authentication, row locking and expected revisions serialize decisions; stale revisions return conflicts. Actor IDs and prior/new states remain in append-only history.
6. **What does your success rate measure?** Terminal successes divided by successful and failed/timed-out outcomes within a selected completion window, excluding cancellation. Attempt retries are counted by start time. It is not an SLA.
7. **What did backup verification prove?** A transaction-consistent `pg_dump` restored into a new isolated database with matching row fingerprints for all 24 tables. It did not test RDS disaster recovery or cluster-role restoration.
8. **Which optimization has evidence?** On 10,000 artificial history rows, the migration-007 pipeline/history index changed a scan/sort to an index scan: 4.667ms versus 0.068ms in one local EXPLAIN experiment. Production gains require representative workloads/repeated measurements.
9. **How do you keep public registry data honest?** Retain official provenance, bounded selection scope, capture/replay labels and field-level validation. Never join synthetic clinical scores to registry identities. Checksums detect corruption, not provenance forgery.
10. **What prevents production readiness today?** The real CMS archive is missing; AWS/TLS/RDS privileges and failover are unverified. Single-host availability, production identity lifecycle, external immutable audit, rotation/paging and operational ownership need review. The application is demonstrable locally, not certified for sensitive clinical use.

For a Garner engineer: FastAPI/SQLAlchemy/Alembic and PostgreSQL own durable state; React/TypeScript present the same evidence through authenticated endpoints; a small Python supervisor handles execution isolation, retries and leases. The most important design choice is making every outcome inspectable while keeping source identity, authorization and publication integrity explicit.

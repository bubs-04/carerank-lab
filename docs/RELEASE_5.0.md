# CareRank 5.0 delivery

Baseline: latest fetched `main` at `7d9111cde77eb44dd9b4ba259e73753a1ebeeb3d`, including merged CareRank 4.0 PR #4 and migration 005. Feature branch: `feat/pipeline-orchestration`.

## Changelog

- Added migration 006 with persistent pipeline definitions, executions, attempts, append-only events, claim/idempotency constraints and scheduling/recovery indexes. Retained databases upgrade forward; downgrade is restricted to `carerank_test`.
- Added PostgreSQL scheduling, concurrent worker claims, independent heartbeats, leases, per-attempt timeouts, bounded exponential retries and recovery of interrupted work.
- Connected existing CMS/fixture ingestion and monitoring through fenced publication and a durable publication checkpoint. Identical content reuses snapshots; post-publication recovery reconciles monitoring without refetching.
- Added authenticated trigger/cancel/retry APIs, Administrator policy configuration, revision conflicts and identity-linked decision history.
- Added the responsive Pipeline Operations workspace: schedules, execution state totals, filters, attempt timelines, failure reasons, recovery controls and links to existing evidence.
- Added separate worker database credentials/grants to Compose, setup and CI. The cloud helper receives the matching minimal runtime correction; authentication stays enforced.
- Added deterministic first-attempt failure/recovery and PostgreSQL concurrency, process-termination, security, preservation and UI regressions. Live CMS remains optional.

No ranking formula, synthetic replacement policy or prior snapshot/incident model is replaced. No merge, public deployment or repository visibility change is part of this delivery.

## Five-minute technical demonstration

Use an isolated development stack whose API **and worker** target `carerank_test`, with migration 006 and development Administrator/Analyst/Viewer accounts. Keep the worker running and monitoring enabled. Do not reset the retained `carerank` database. No live CMS calls are needed.

1. **0:00–1:00 — Schedule.** Sign in as Administrator and open **Pipeline operations → Create a pipeline**. Name it `Recovery demonstration`; select **Development recovery demo**, 5 requested rows, 3600-second interval, 2 maximum attempts, 5-second initial backoff and 30-second timeout. Check **Enable scheduled ingestion** and create it. Explain that its first run is due immediately and that the policy is copied into the execution.
2. **1:00–2:00 — Observe failure and recovery.** Select its latest execution; use **Refresh** or allow polling. Attempt 1 records `demo_transient_failure`, then the execution enters `retry_wait`. After the policy delay, attempt 2 succeeds using fixture A. If the transition finishes before the screen refreshes, both attempts and their timestamps remain visible. Show the scheduled trigger and `queued`, `claimed`, `retry_scheduled` and `succeeded` events.
3. **2:00–3:00 — Inspect evidence.** Open the failed attempt's ingestion evidence to show the recorded failure and quality evaluation. Return and open **Inspect ingestion and quality evidence** for the successful publication. Show its fixture provenance, snapshot and quality results. A retry's success does not erase the failure history or resolve an incident automatically.
4. **3:00–4:00 — Prove repeatability.** Return to Pipeline operations and choose **Run Recovery demonstration now**. Its independent execution again fails once and recovers. Compare its published snapshot with the previous execution: unchanged fixture content reuses the same snapshot while execution/attempt audits remain distinct. Pause the schedule through **Edit schedule and recovery policy** after the demonstration.
5. **4:00–5:00 — Show access and recovery guarantees.** Sign in as Viewer: schedules, history and evidence remain readable, control forms are absent. Explain that backend tests also reject forged Viewer requests and missing CSRF. Show the PostgreSQL process-termination test evidence for `test_terminated_worker_leaves_recoverable_attempt`: a killed worker leaves an interrupted attempt, a new claim succeeds and stale publication is fenced. State the guarantee precisely: at-least-once delivery with idempotent publication.

For an explicit terminal-failure/manual-retry demonstration, create a separate paused development-demo definition with one maximum attempt, run it and inspect `failed`; **Retry execution** creates a new linked execution with the same one-attempt policy. It deliberately fails again because each execution's first attempt is the fault scenario. Use two or more attempts to demonstrate automatic successful recovery.

## Verification status

- **PostgreSQL migration 005 → 006:** main development database upgraded successfully. All 18 pre-existing tables retained identical row counts and SHA-256 hashes of their sorted row JSON, including 1,000 providers, 100,000 encounters, 1,000 scores, registry snapshots/runs, authentication data, evaluations, alerts and audit events. Preservation was rechecked after verification. Destructive tests used only `carerank_test`.
- **Backend:** full PostgreSQL/unit/security regression run: 215 passed; 1 optional live CMS test skipped (133.72 seconds). After the final permission-cleanup and history-pagination changes, all three affected PostgreSQL tests passed. The operations module now contains 23 tests, including real worker termination, contention, fair claiming, retry fencing and restricted API/worker permissions.
- **Frontend:** 58 component tests passed in the full run; the subsequent Pipeline Operations rerun passed all 9 tests, including new history pagination. Final TypeScript/production build, Ruff lint/format and Prettier checks passed; launcher tests: 4 passed. The separate live React → Vite → FastAPI → PostgreSQL workflow passed. All 11 Chromium workflows passed across the full run (10 passed) and the corrected pipeline rerun (1 passed, 20.7 seconds). The latter proves scheduled deterministic failure, automatic recovery, exact attempt/event history, evidence navigation, schedule pause and 390px mobile layout. Browser findings fixed: wait for the loaded form, use the accessible source control, expect the documented `queued` event, and constrain the grid so its scrollable table does not widen the mobile page. No assertion was removed. [Browser evidence](pipeline-operations-5.0.png).
- **Review fixes:** bounded heartbeat retries tolerate legitimate publication lock contention; oldest ready work prevents starvation; manual retry inserts publication checkpoints without expanding API grants; reconciliation locks interrupted runs; provisioning clears old column ACLs. Execution history has pagination. The initial concurrent local live React check exceeded its short data-load wait, then passed unchanged when run alone. These fixes retain all assertions and permissions.
- **GitHub CI:** pending draft PR verification. CI uses deterministic fixtures and restricted runtime logins, runs the complete suites, and verifies the actual Nginx proxy boundary. Shared-account browser workflows run sequentially; worker concurrency is tested directly against PostgreSQL.

No live CMS retrieval, production deployment, database failover/load test or independent human security audit is claimed. Existing non-failing Starlette/httpx deprecation and Lucide bundler warnings remain.

## Operational limitations

A worker and healthy PostgreSQL are required for scheduling, retries and lease recovery. Missed intervals coalesce; the queue is bounded and does not promise every elapsed interval will run. The fixed-interval scheduler is not a cron/calendar scheduler. Delivery is not exactly once. History retention, external notifications, production identity/secret delivery, backup/failover and deployment monitoring remain operator responsibilities. See [the architecture](ARCHITECTURE_5.0.md) and [existing security boundary](SECURITY_4.0.md).

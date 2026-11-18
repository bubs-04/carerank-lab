# CareRank 6.0 release evidence and limitations

Baseline: merged CareRank 5.0, `4b34e16`; feature branch `feat/enterprise-platform-v6`. This is a review candidate, not a production deployment or a completed real-CMS showcase. No AWS resources, public deployment, merge or Mac database changes were performed.

## Change summary

- Migration 007 adds worker presence and history/metric indexes. Existing schemas and durable data remain intact; runtime grants separate API reads from worker presence writes.
- Structured request/execution logging, UUID correlation, read-only authenticated aggregate metrics, migration readiness/liveness, worker health, bounded PostgreSQL waits and mounted-file secrets.
- Accessible Reliability workspace: explicit outcome denominators, duration percentiles, hourly counts, retries, queue age, stale leases, worker readiness and links to pipeline/quality evidence. Errors retain prior evidence and show a request ID. CMS archive replay is labeled separately from fresh retrieval.
- Dedicated local demo, private random development accounts, idempotent preparation, guarded reset and optional verified offline CMS archive support. Schedule/failure/retry/audit demonstration uses explicitly artificial fixtures.
- Standalone hardened production Compose, minimal AWS CloudFormation reference, release manifest/secret/deployment helpers, static CI validation and a manual review receipt workflow with no AWS permissions.
- Central [architecture](ARCHITECTURE_6.0.md), [Garner demonstration](DEMO_6.0.md), [cloud runbook/threat boundaries](../infra/README.md), and reproducible recovery/load script.

## Actual PostgreSQL and reliability measurements

Measured in the isolated Codex Linux development environment on 18 November 2026. PostgreSQL 16.16, disposable container limited to 2 CPUs/512MiB; host exposed 3 logical CPUs. No result is a production SLO or capacity estimate. Raw measurements and query plans: [RELIABILITY_6.0.json](RELIABILITY_6.0.json). That run used backend checkpoint `657ca83` plus the then-uncommitted verification script; the recorded Git SHA is not a claim that the script was already committed.

| Verification | Observed result |
|---|---|
| Main 006 → 007 | All 22 original tables retained identical sorted-row content hashes and counts. Includes 100,000 encounters; 1,000 providers/scores each; 2 registry snapshots/10 records; 8 alerts/8 monitoring events; 3 accounts and 5 auth events. No original data changed. |
| Consistent logical backup/restore | All 24 table fingerprints matched in a new isolated database; backup plus fingerprinting 1.616s, restore 1.816s. Private dump removed afterward. |
| Restore migration check | Backup was already 007, so 007 → 007 was correctly recorded as a no-op. It is **not** the separate 006 → 007 preservation claim. |
| Worker killed during fixture fetch | Natural 3-second lease expiry; replacement succeeded in 5.981s. Attempts: interrupted → succeeded; one published snapshot. |
| PostgreSQL force-stop/restart during active fetch | Read failed while down; same supervisor survived; DB ready in 6.551s, execution succeeded in 9.810s. Interrupted → succeeded; one snapshot; synthetic counts unchanged. |
| Synthetic query load | 240 filtered search/count/page/serialization operations, 8 concurrent clients, 30 warmups: 0 errors; p50 51.923ms, p95 147.409ms, max 364.471ms; 117.63 operations/s. In-process database calls, **not HTTP latency**. |
| History index experiment | 10,000 artificial history rows; latest 50 of one pipeline: scan/sort 4.667ms versus backward history-index scan 0.068ms. One controlled EXPLAIN experiment, not a generalized speedup. |
| Running demo | Scheduled execution failed with `demo_transient_failure`, then succeeded automatically with two attempts, linked snapshot and complete queued/claimed/retry/success events. Metrics showed one retry and a healthy worker. Anonymous/CSRF/Viewer negative checks passed. |

Reproduce with the backend dependencies and a local PostgreSQL 16 image:

```bash
# DATABASE_URL identifies the read-only backup source. Never put it in shell history.
python scripts/verify_reliability.py --source-container carerank-cloud-db
```

The script only reads the source, creates its own randomly named/labeled Docker container on a separate explicit loopback port, restores into `carerank_restore_test`, and runs destructive experiments against its own `carerank_test`. It validates ownership and rejects retained mounts/port 5432 before removal. It does not use the shared test database. Backups exclude cluster roles; runtime users must be provisioned separately. Presence is transient and is the only telemetry with seven-day pruning; execution/audit retention remains unchanged.

## Regression evidence

Independent [GitHub CI run 44421707687](https://github.com/bubs-04/carerank-lab/actions/runs/44421707687) **passed** on application commit `65f8854fbcc61d8f01f08d245a2fbf80a8b22222`: **233 backend tests passed, 1 optional live-CMS test skipped; 65 frontend tests, 15 script tests and 12 Playwright workflows passed**, along with lint/formatting/build, CloudFormation validation and real reverse-proxy source-isolation/spoofing checks. The subsequent evidence/architecture update changes documentation only; application and test source remain identical to the verified commit.

The initial local full backend run had 231 passes, 1 optional live-CMS skip and 1 stale migration assertion expecting 006 after upgrading to `head`. That test was corrected and expanded to verify preservation from both 005 and 006 through 007, with populated execution/attempt/snapshot history for 006. Both focused cases and the independent full CI suite then passed without removing preservation assertions.

Frontend: **65 tests passed** against the running restricted-role PostgreSQL API, including the live workflow; TypeScript/production build and formatting passed. Script safety/launcher tests: **15 passed**. Ruff checks/formatting passed. CloudFormation `cfn-lint`, release-manifest validation and production Compose interpolation passed without provisioning anything. Backend and web container builds passed using a temporary BuildKit CA secret for this environment's TLS proxy; no CA or credentials were baked into images.

Browser: **12 Playwright workflows passed** with the environment's configured Chromium, including schedule/failure/retry, Viewer/mobile reliability, authentication/CSRF/role denials, incident lifecycle, snapshot comparisons, ranking, analytics and Refresh status. [Actual Reliability screenshot](reliability-6.0.png) and [pipeline recovery screenshot](pipeline-recovery-6.0.png) come from that running application. GitHub independently passed the same 12 workflows. Historical 3.x–5.x reports are not substituted for current checks.

The containerized demo also passed guarded volume reset, offline restart and the scheduled recovery demonstration a second time. Repeated preparation preserved all 23 durable table fingerprints (excluding transient worker presence). The production Nginx configuration passed syntax validation as UID 101 with a read-only filesystem, dropped capabilities and its configured temporary filesystem; its non-secret bind-mounted configuration must be readable by that UID (normal checkout mode 0644).

## Audit findings, corrections and remaining gates

Reviewed worker claiming/publication fencing, lease recovery, cancellation/reconciliation, auth/CSRF/role rechecks, role grants, migration boundaries and deployment secret handling. Existing queue/authentication behavior is preserved. Corrections include the stale migration test, stable Docker port across restart in the verification harness, clearing the cached Alembic engine between two isolated databases, accepting RDS's generated owner-password length without lowering runtime-password requirements, ignoring shell overrides of validated release settings, and recreating Nginx with the API so its upstream address is refreshed.

**Real public CMS capture remains blocked:** the managed network permits package-manager hosts but denies `data.cms.gov` with proxy HTTP 403. Archive code and corruption/source-scope tests are implemented, but no genuine archive or live ingestion is claimed. Complete the reviewed capture in [demo/README.md](../demo/README.md) before calling the entire Garner demo ready. CI stays deterministic and offline from CMS.

**Production remains unverified:** AWS provisioning, actual ALB TLS/client-IP behavior, RDS role privileges/failover/restore, secret rotation and host reboot recovery, high availability, production identity lifecycle/SSO/MFA, external immutable audit retention and paging are not tested. See the [cloud threat model and runbook](../infra/README.md). The single-host design has an explicit availability limit. Static templates and local recovery are useful evidence, not proof of cloud production reliability.

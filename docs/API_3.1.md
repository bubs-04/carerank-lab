# CareRank 3.1 monitoring API

All endpoints below are read-only GETs under `/api/dataops/monitoring`. Swagger is available at `http://localhost:8000/docs`; the generated contract is [monitoring-openapi.json](monitoring-openapi.json). No endpoint accepts alert mutations, ingestion triggers, an operator identity, or an arbitrary external URL. `POST`, `PUT`, `PATCH`, and `DELETE` on alert detail return 405.

| Path | Query/input | Response and purpose |
|---|---|---|
| `/summary` | `mode=cms` or `fixture` | Latest attempt, current profile hash, expected rule count, evaluation counts, unresolved alerts by severity, explicit health and explanation |
| `/rules` | None | Current configured definitions; each includes rule ID, algorithm version, content hash, description, severity, threshold and unit |
| `/runs/{run_id}` | Registry run UUID | Exact attempt metadata, including status, requested/received counts and source provenance; 404 if absent |
| `/evaluations` | mode; optional run_id; current_only=true; page=1; page_size=20 | Evaluation history, threshold, observation, rule version, baseline and reproducible evidence; `current_only=false` includes older configurations |
| `/alerts` | mode; optional status and severity; pagination | Durable alerts across all configurations, including resolved alerts; severity warning/critical; lifecycle status enum |
| `/alerts/{alert_id}` | Alert UUID | Alert plus the immutable originating evaluation; 404 if absent |
| `/alerts/{alert_id}/events` | pagination | Investigation events, newest revision first; preserves creation, assignment, decisions and resolution notes |
| `/trends` | mode; optional successful run_id; limit=20 (1–50) | Oldest-to-newest retrieval counts for the same source, scope and validation policy as the reference; only successful attempts, including version reuse |

Pagination requires page >= 1 and page_size 1–100. Invalid inputs return 422. A missing alert/run returns 404. A trend reference from a different mode or an unsuccessful attempt returns 422. Database errors return a sanitized 503; invalid DQ configuration returns 503 on current-profile endpoints. HTTP headers never identify an investigator.

`observed: null` means unavailable. It must never be plotted as zero. `passed` means observation <= threshold, `failed` means observation > threshold, and `not_evaluable` means the metric or compatible baseline is unavailable. Evidence includes numerator counts, denominators, source/scope/policy, baseline IDs, comparison counts and bounded-prefix limitations.

Health is `no_data`, `disabled`, `pending`, `attention`, `partial`, or `passed`. Only `passed` is green: the latest attempt has all 12 current-profile evaluations, none failed or unavailable, and there are no unresolved alerts in that source mode. It is not a freshness, clinical quality, national coverage or data certification claim. Older attempts may still need backfill; latest-attempt coverage is labeled explicitly.

Example:

```bash
curl -fsS 'http://localhost:8000/api/dataops/monitoring/summary?mode=fixture'
curl -fsS 'http://localhost:8000/api/dataops/monitoring/evaluations?mode=fixture&page_size=20'
curl -fsS 'http://localhost:8000/api/dataops/monitoring/alerts?mode=fixture&status=open'
```

Existing `/api/dataops/runs/{id}/findings`, `/versions/{id}/records`, `/compare`, and all synthetic analytics APIs are preserved. New evidence buttons open those existing panels through React state; no router rewrite was introduced.

## Local write interface

```bash
docker compose run --rm --no-deps api python -m app.monitoring evaluate --mode cms --limit 100
docker compose run --rm --no-deps api python -m app.monitoring evaluate --run-id RUN_UUID
docker compose run --rm --no-deps api python -m app.monitoring inspect ALERT_UUID
docker compose run --rm --no-deps api python -m app.monitoring investigate ALERT_UUID --actor 'Prabhat' --expected-revision 1 --status investigating --assign 'Prabhat' --note 'Reviewed source scope and validation evidence.'
```

Replace uppercase placeholders with IDs from the dashboard. `inspect` prints the current revision and full audit history. `--actor` is a self-reported label from the trusted local operator, not an authenticated account. Without `--status`, investigate appends a note and optionally changes assignment. `--assign ''` clears assignment. A note is required for every action. Expected revision must equal the current revision; stale decisions fail without writing. Notes are 1–2000 characters; actor/assignee at most 100 characters.

Allowed transitions: open → acknowledged/investigating; acknowledged → investigating/resolved; investigating → acknowledged/resolved; resolved → open. Resolution requires the same mandatory note; reopening clears the current resolution field but retains the original resolution event. Re-evaluation never automatically resolves or reopens alerts.

An explicit evaluation works even with automatic `DQ_ENABLED=false`. Backfill processes up to the limit of oldest terminal attempts missing the current profile; repeat until `evaluated_attempts` is zero. An explicitly selected running attempt returns pending without persisting misleading results. CLI errors exit 1; no exception details containing database credentials are printed.

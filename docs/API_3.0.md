# Data Operations API

All routes are read-only GET requests under `/api/dataops`. Live CMS ingestion is initiated only by the local CLI. There is no ingestion POST route and no user-supplied network URL. Existing APIs are unchanged. Interactive schema: http://localhost:8000/docs. Generated full OpenAPI contract: `docs/dataops-openapi.json` (includes existing routes as well).

| Route | Inputs | Response |
|---|---|---|
| `/status` | `mode=cms` or `fixture` (default cms) | Sources, latest attempt, latest successful/reused run, snapshot count |
| `/versions` | mode, page ≥1, page_size 1–100 (default 20) | Published version history, total/page/page_size |
| `/runs` | Same pagination and mode | All attempts, including failures and running jobs |
| `/runs/{run_id}/findings` | page, page_size (default 50) | Row/batch findings; row number, severity, rule code, field |
| `/versions/{snapshot_id}/records` | page, page_size (default 50) | Projected accepted and rejected source records, no clinical scores |
| `/compare` | old_id, new_id (required) | Added/removed/changed/unchanged counts, specialty/location changes, finding deltas and bounded examples |

Unknown run/version: 404. Invalid pagination/mode or incompatible comparison scope: 422. Database/schema errors: sanitized 503. A comparison with the same version returns all accepted records unchanged. “No change” run status means content matched an existing version in the catalog; the UI says “Version reused.” It may be a reversion to an older version.

```bash
curl -fsS http://localhost:8080/api/dataops/status
curl -fsS 'http://localhost:8080/api/dataops/versions?mode=fixture&page_size=10'
curl -fsS 'http://localhost:8080/api/dataops/runs?mode=cms&page_size=10'
# Replace IDs below with IDs returned above:
curl -fsS 'http://localhost:8080/api/dataops/runs/RUN_ID/findings?page_size=50'
curl -fsS 'http://localhost:8080/api/dataops/versions/VERSION_ID/records?page_size=50'
curl -fsS 'http://localhost:8080/api/dataops/compare?old_id=OLDER_ID&new_id=NEWER_ID'
```

Version metadata includes source ID, captured time, ordered projected-content SHA-256, sampling scope, policy version, source release/modified/issued values when supplied, download URL, distribution ID, counts and findings histogram. Runs record retrieval start/end, duration, requested/received counts and the outcome. A failed transport may have unknown received counts; null is not presented as zero.

Comparison uses accepted identities only. `added + changed + unchanged` equals the newer accepted total; `removed + changed + unchanged` equals the older accepted total. `location_changes` counts changes in city/state among stable keys. Changed address IDs become removals/additions, not inferred relocations. Row rejection can also remove an identity from accepted membership. Finding deltas count findings, not necessarily distinct rows. At most 50 changed-record examples and 20 added/removed examples each are returned; totals remain complete for the bounded snapshots.

Fixture and CMS source modes cannot be compared, nor can different row limits or validation policies. The UI lists latest runs independently from successful snapshots so a failed job cannot erase the last good version.

## CLI and configuration

```bash
python -m app.ingestion --max-rows 1000
python -m app.ingestion --fixture tests/fixtures/cms_registry_a.csv --max-rows 5
python -m app.ingestion --mark-interrupted ACTUAL_RUN_ID
```

The final command is for explicit recovery only after confirming the worker has stopped. SIGTERM/KeyboardInterrupt are handled; SIGKILL/power loss may leave a visible running audit. Database outages can prevent failure-audit updates. No job scheduler or heartbeat service is implied.

| Environment setting | Default | Allowed |
|---|---|---|
| DATABASE_URL | Required, existing configuration | PostgreSQL URL for normal deployment |
| CMS_MAX_ROWS | 1000 | 1–5000, exact target prefix length |
| CMS_TIMEOUT_SECONDS | 20 | 1–60 per HTTP operation |
| CMS_DEADLINE_SECONDS | 120 | 10–300; checked between network chunks/requests; a blocking operation can extend it by its timeout |
| CMS_MAX_BYTES | 8000000 | 1000–25000000 decoded CSV bytes |
| CMS_ATTEMPTS | 3 | 1–4 complete attempts |
| CMS_LIVE_TEST | unset | `1` explicitly enables the optional network test |

Transient transport/429/5xx failures retry from the beginning with bounded exponential backoff. Permanent HTTP failures and contract errors do not retry. Metadata responses are capped at 1 MB. Redirects are not followed. Only HTTPS `data.cms.gov` CSV URLs under the official provider-data files path are allowed. TLS verification remains enabled. The connector does not accept arbitrary endpoint configuration.

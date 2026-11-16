# CareRank 3.0 — Data Engineering Guide

Prabhat Mattaparthi · Independent engineering portfolio · 15 November 2026

Public provider registry, separate from the synthetic ranking lab. No patient records or clinical ratings.

## 1. What ingestion means

Data ingestion is the process of bringing data from another system into a system you control, checking it, and recording what happened. Downloading a file is only the first part. A trustworthy ingestion job can answer where the data came from, which release it represented, what was accepted or rejected, whether the operation finished, and how it differs from a previous capture.

CareRank's new subsystem does that for public provider-registry information. It is deliberately separate from the original fictional provider/encounter/score pipeline. The registry does not assign a medical score to CMS clinicians, and there is no foreign key or join connecting their identities to fictional outcomes.

Think of the existing ranking lab as a practice worksheet and the public registry as a dated directory. Mixing the real names in a directory with invented grades from a worksheet would be misleading. The architecture prevents that combination rather than relying only on a disclaimer.

This release extends the exact CareRank Lab 2.0 ZIP previously delivered. The private GitHub repository could not be authenticated, so newer branch changes were not inspected. A local branch named feat/cms-data-ingestion holds an isolated baseline; the supplied patch must be checked against your actual branch before application. Nothing was pushed, merged or deployed, and your existing Mac database was not changed.

## 2. REST APIs and the CMS source

A REST API lets one program ask another program for a resource over HTTP. A GET request reads information. The server returns a status code and a body, commonly JSON. A 200 response means the HTTP request succeeded; it does not guarantee the data is valid. A 403 indicates access was denied. A 503 commonly indicates a temporarily unavailable service. CareRank separately validates the response and the records.

The official dataset is the Doctors and Clinicians National Downloadable File, identifier mj5m-pzi6. CMS documents source rows at clinician/enrollment/group/address granularity. One clinician may therefore appear on several rows. NPI alone is not the record key.

The dictionary identifies the relevant key as NPI, individual enrollment ID, group PAC ID and address ID. Group PAC ID may be blank. CareRank retains those four fields plus primary specialty, city and state. It does not retain names, street-address lines, telephone numbers, ZIP codes, or patient information. The address ID is retained because it is part of the documented source identity; it is a source identifier and may encode location-related characters.

The official API distinguishes metadata from data. CareRank GETs the metadata endpoint, validates the public dataset identifier and resolves its CSV distribution. It then streams a bounded prefix from the official CSV resource. The initial datastore row-query probe returned HTTP 403 here; metadata and the official CSV succeeded. This is a real bounded-download connector, not mocked production API data. The tests use fixtures explicitly and separately.

Official references consulted:

- https://data.cms.gov/provider-data/dataset/mj5m-pzi6
- https://data.cms.gov/provider-data/about (API FAQ)
- https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/physician/DOC_Data_Dictionary.pdf
- https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/mj5m-pzi6?show-reference-ids

CMS metadata is authoritative for the source release when present. The retrieved release was November 12, 2026. Public access is not a claim of clinical fitness or an unrestricted license for every use; any license metadata is retained if supplied. Review current CMS definitions and usage conditions before repurposing the source. This project is not affiliated with CMS or Garner.

## 3. Follow the connector step by step

Start with `backend/app/ingestion/connector.py`. CMSConnector.fetch opens an HTTP client with TLS verification, timeouts and redirects disabled. It fetches bounded JSON metadata, checks the dataset and public-access marker, and allows only HTTPS CSV resources on data.cms.gov under the provider-data files directory. An arbitrary URL supplied by an HTTP caller cannot become a network destination.

The CSV is streamed. It is not downloaded in full and then sliced. The line iterator handles UTF-8 and preserves newlines for Python's CSV parser, including quoted multiline fields. The parser normalizes column headings, verifies the required contract, reads exactly the requested number of complete rows and projects only the seven allowed fields. Unused CSV columns pass through the stream but their values are never retained in the registry or logs.

Default requested size is 1,000 rows; the hard upper limit is 5,000. The connector deliberately requires a complete requested prefix. If the stream ends with fewer rows, it fails as incomplete instead of publishing a smaller snapshot without warning. Byte limits and elapsed-time checks bound resources. Deadline checks occur between network chunks/operations; a blocking operation may extend wall time by its configured timeout.

After reading the prefix, the connector fetches metadata again. If release/distribution/resource metadata changed, the batch fails. This prevents knowingly combining a download with a different announced release. It is not a cryptographic guarantee that an upstream file is immutable or that CMS's metadata is perfectly synchronized.

Transient transport failures, HTTP 429 and 5xx failures retry the whole bounded retrieval from the beginning. A retry never appends to a failed attempt's partial rows. Backoff grows by powers of two with a cap, and attempts are bounded. Permanent HTTP failures, schema errors and provenance-contract violations fail immediately. Errors store safe codes, not remote response bodies or arbitrary provider values.

For CI, fixture_batch reads an explicitly supplied local CSV through the same parser. Its source mode is fixture, and it has a different source ID and history from live CMS. It cannot be confused with a real retrieval by a hidden fallback: CMS failure never automatically turns into fixture success.

## 4. Validation: blank is not always broken

A missing optional value is different from an invalid row, and an invalid row is different from a failed batch. CareRank makes those three levels visible.

At the row level, NPI must have ten digits starting with 1 or 2. Enrollment IDs must be fifteen alphanumeric characters. Nonblank group PAC IDs must have ten digits. Address IDs must be nonempty and at most twenty-five characters. These are local shape checks based on the source contract; NPI assignment and check digits are not validated.

Missing specialty, city or state values produce warnings. Overlong specialty/city values, unknown state codes and control characters reject a row. Every finding contains a row number, severity, rule code and field. One row can have multiple findings. Warning counts are not an additional category to add to valid/rejected totals.

Duplicate detection uses the full four-part source identity. All occurrences of a duplicate key are rejected, even when their content is identical. There is no arbitrary first-row-wins rule. A clinician with the same NPI and a different address or enrollment remains a distinct valid source record.

At the batch level, missing required columns, colliding normalized headers, malformed CSV, a short prefix, an empty batch or no valid records prevent publication. Additional unknown columns produce warnings and their values are ignored. A mixed batch with at least one valid row can publish both accepted and rejected projected rows, with counts and findings; no rejection-percentage quality gate is implied.

Review `VALIDATION_3.0.md` for the complete rule table. Successful processing is not the same as high data quality, and registry completeness is not clinical quality. The UI presents run status separately from validation outcomes for this reason.

## 5. Three different identities

A record key answers “which source-level record is this?” It hashes a canonical JSON array of NPI, enrollment, group and address ID. Changing specialty or city while retaining that key is a field change. Changing the address ID changes identity and appears as removal/addition; the system does not infer a clinician moved.

A content checksum answers “is this the same captured projection?” It covers selected raw values in captured row order plus normalized header names. It does not cover the complete national file. Ignored phone/name changes are outside scope. Row order is retained because findings refer to source row numbers; reusing a reordered capture could otherwise point findings at the wrong stored row.

A snapshot scope answers “what population did we try to capture?” It records source-order prefix selection, row target and projected fields. A 1,000-row capture and a 5,000-row capture are not comparable. Live CMS and fixtures are not comparable. Validation-policy versions must also match.

The version uniqueness rule combines source, scope hash, content checksum and policy. Identical captures reuse an existing version. A later reversion to older content also reuses that older version; the run status no_change means no new catalog version, not necessarily no change from the immediately preceding retrieval. The UI calls it Version reused.

## 6. How PostgreSQL stores the history

Migration 002 adds six tables and does not alter the original synthetic tables.

| Table | Purpose and important relationship |
|---|---|
| registry_sources | Source identifier, dataset, mode, title and URL; fixture and CMS are separate rows |
| registry_runs | One attempt, including running/failed/interrupted/reused status, timestamps, duration, counts, safe error and provenance |
| registry_snapshots | Published version metadata, scope, policy, checksum and validation counts; content uniqueness constraint |
| registry_records | Projected accepted/rejected rows per snapshot; source row number, record key and content hash |
| registry_findings | Row-level and batch-level findings attached to an attempt |
| registry_changes | Stored summary for a newly published version versus the preceding compatible successful retrieval |

RegistryBase is separate from the original SQLAlchemy Base. Both metadata collections are known to Alembic. Migration 002 contains frozen table definitions so future model edits cannot silently rewrite the historical migration. Downgrading to 001 drops registry history only; downgrading to base would also remove the original schema and is not an upgrade-recovery shortcut.

The records table has a unique accepted identity per snapshot. Rejected duplicates use a null accepted key, so they can be retained without violating that constraint. Snapshot counts must reconcile: received equals valid plus rejected, with at least one valid record and at most 5,000 received rows.

Read endpoints use SQL filtering, count queries, stable ordering and bounded pagination. Comparisons load only the two bounded registry projections into Python, never the encounter dataset. This is appropriate for the release's small captures; larger production workloads would require measured query/index and retention design rather than assuming this architecture scales indefinitely.

## 7. Transactions protect the last good result

Imagine a job inserts a new version header, writes half its records, and crashes. Without a transaction, the UI might show an incomplete version as successful. CareRank avoids that by separating an attempt audit from snapshot publication.

Transaction one creates the running audit and commits it before network work. Fetching and validation happen outside database transactions. That avoids holding locks while waiting for CMS.

Transaction two acquires a short PostgreSQL advisory transaction lock, checks whether a matching version already exists, and atomically writes the version, projected rows, findings, comparison summary and final successful run state. A unique constraint also protects version identity. Lock acquisition has a ten-second timeout. If any write fails, the entire publication transaction rolls back.

A separate failure transaction marks the attempt failed or interrupted and retains available counts, provenance and findings. Earlier snapshots are not deleted or modified. Tests inject a failure immediately before commit and prove no partial snapshot, source rows or comparison survives.

Normal interruption and SIGTERM can finalize the audit. SIGKILL, power loss or database unavailability cannot always do so; a job may remain visibly running. The explicit mark-interrupted CLI command is an operator recovery action, used only after confirming the worker stopped. There is no invisible background scheduler or heartbeat service in this release.

Concurrent PostgreSQL publication is serialized only during short write transactions. No database lock is held while downloading. Concurrency tests are implemented but were not executable here because PostgreSQL/Docker access was blocked. SQLite tests do not certify PostgreSQL advisory locking.

## 8. Comparing two versions

`compare_versions` first verifies both published versions exist and have the same source, scope and validation policy. It then compares accepted records by their source identity.

Added records exist only in the new accepted set. Removed records exist only in the old accepted set. Changed records retain identity but differ in a tracked field. Unchanged records retain identity and equal tracked fields. These categories are disjoint within the appropriate old/new totals.

The engine enumerates changed fields, counts primary-specialty changes and counts city/state changes among stable identities. It also calculates finding-count differences, newer minus older. A single record can contribute to both specialty and location change counts, so those counts are not categories to add to the main partition.

The API returns exact totals and bounded examples, not all records in the browser. At most fifty changed records and twenty added/removed examples each are returned. The GUI's comparison table shows changed fields with before/after values. Separate record-inspection endpoints provide pagination through either snapshot.

The source is a bounded prefix, not a national census. An insertion early in a CSV may push a record beyond the cutoff. A validation rejection can also remove a previously accepted identity. Neither event proves that a clinician stopped practicing or left Medicare. The API and UI carry this caveat alongside the chart.

Fixture A versus B intentionally yields one added, one removed, one changed and two unchanged accepted records. One retained row changes specialty and city. Reversing the comparison reverses before/after values. Reordering a capture can create a new checksum while comparison reports all accepted identities unchanged. Reverting to an older version is tested so the next stored comparison uses the last successful retrieval, not merely the newest version creation time.

## 9. Using the Data Operations page

Open Data operations from the existing sidebar. Live CMS is the default mode. The fixture selector is explicit and prominently labels artificial records. The ranking pages retain their synthetic disclaimers; the DataOps page describes public registry records and test fixtures instead.

Source/job health shows the latest attempt separately from the last successful retrieval. A failed new attempt therefore does not hide the last good snapshot. Counts distinguish requested, received, valid, rejected and warning findings. Unknown counts display as unknown or a dash, not zero. The duration is recorded job time, not a performance benchmark.

Version history shows captured time, release when supplied, row scope, counts, checksum and policy. Records opens a paginated projected-record table. Set older and Set newer choose a comparison, including versions selected across history pages. Cross-scope comparisons return a clear API error instead of misleading charts.

The comparison chart explains sample membership and exposes validation deltas and before/after examples. Ingestion attempts include failed and interrupted runs. Findings can be opened for the latest run or any run in history. Record and findings tables have bounded pagination and clear empty states.

All new requests use the existing useApi hook and its stale-response guard. Switching source mode remounts the workspace, resetting selections; old responses cannot overwrite current data after cancellation. Refresh status reloads the page after a CLI job. There is intentionally no Run ingestion button and no HTTP write endpoint.

## 10. Verification evidence and gaps

The final backend suite passed 67 tests; 16 PostgreSQL integration tests and one opt-in live test were skipped. Frontend tests passed 20 with one optional live-DOM test skipped. TypeScript/Vite build, Ruff and Prettier passed. SQLite migration up/down/up preserved a synthetic sentinel row.

Separate from the opt-in pytest test, the actual finalized CLI performed a live 1,000-row CMS retrieval, accepted all 1,000, and recorded zero warning findings. Those rows represented 421 distinct NPIs, illustrating multiple source records per clinician. A second finalized live retrieval reused the same snapshot; one CMS version remained. Both runs used an isolated SQLite database, not PostgreSQL or your existing Mac environment. The provenance and actual IDs/checksum are in `docs/verification/v3/live-result.json`.

The fixture CLI also ran A, B and B again, producing the expected comparison and reusing B. These are explicitly artificial test inputs, not evidence of live CMS API behavior. Default CI uses these fixtures and needs no live CMS access.

Docker configuration parsed, but the engine socket was permission-denied. Playwright attempted Chrome once, which aborted before navigation; one test failed and two did not run. No new screenshots or visual browser pass are claimed. PostgreSQL migrations, concurrent publication and the full browser workflow remain local verification tasks. Remote GitHub CI has not run for these changes.

A SOCKS-proxy support package was installed only in an isolated task dependency directory to exercise the live network path. No application dependency or global Mac installation changed. The production requirements already contain httpx; a host that mandates SOCKS needs its optional socks support explicitly installed in that environment. TLS and network controls were not disabled.

This Word document is structurally validated with an embedded architecture diagram. Its actual Word pagination was not rendered here. Open it in Word or Pages before sharing.

## 11. Safe upgrade and interview preparation

Follow `UPGRADE_3.0_MAC.md`, which starts with the existing branch, database dump, private `.env` backup and before/after synthetic counts. Apply the patch only after `git apply --check` succeeds. If your private branch differs from the delivered 2.0 baseline, provide its current ZIP for reconciliation rather than overwriting it.

Build API/web, run Alembic upgrade head through the API image with --no-deps, then restart API and web with --no-deps. This avoids running the synthetic seed dependency. Keep the existing Compose folder/project name and database volume. Application-only rollback can leave the additive registry tables intact; a downgrade to 001 deletes registry history and needs a new backup and stopped ingestion workers.

Use a separate disposable PostgreSQL database for integration tests; their migration fixture drops/recreates schema. Run the two fixtures before the optional DataOps browser workflow. Review and commit locally only after checks. No push or publication is authorized by this delivery.

A healthcare analytics organization could use this foundation to audit provider-directory updates, detect source/schema changes, review rejected records and reproduce a registry capture used by a downstream job. It is not yet an enterprise production platform: authentication/authorization, scheduling, immutable raw archives, incremental ingestion, monitoring, stronger source validation, retention governance and measured scale remain future work.

For an interview, explain one successful path and one failed path. Show the four-part identity, explain why a missing optional specialty differs from a missing NPI, and describe why a snapshot cannot become half-successful. Be candid that AI assisted implementation and documentation and that PostgreSQL/browser verification still needs your local run. Practice the five exercises and two-minute script before presenting the implementation as understood.

## 12. Function-by-function reference

The following catalog names each new top-level production Python function/method, its inputs, output and core responsibility. Model classes define table/response fields; they do not execute ingestion themselves. Nested validation callbacks are also noted. Read the source beside the catalog and trace a single row through it.

### backend/app/ingestion/__main__.py

| Function and inputs | Output and important logic |
|---|---|
| interrupt(signum, frame) | Raises KeyboardInterrupt for SIGTERM so the active service can record interruption. |
| main() | Parses CLI/config, optionally recovers a confirmed-stopped run, executes ingestion, prints safe outcome and sets exit code. |

### backend/app/ingestion/api.py

| Function and inputs | Output and important logic |
|---|---|
| paged(db, query, page, page_size) | Bounded items plus SQL total/page/page_size; caller supplies stable ordering. |
| status(db: DB, mode: Literal['cms', 'fixture']='cms') | StatusView payload with independent latest attempt and latest successful/reused retrieval. |
| versions(db: DB, mode: Literal['cms', 'fixture']='cms', page: Page=1, page_size: Size=20) | Published SnapshotPage, filtered by explicit CMS/fixture mode. |
| runs(db: DB, mode: Literal['cms', 'fixture']='cms', page: Page=1, page_size: Size=20) | RunPage including failed/running/reused attempts, filtered by source mode. |
| findings(run_id: str, db: DB, page: Page=1, page_size: Size=50) | FindingPage for an existing run; missing run gives 404. |
| records(snapshot_id: str, db: DB, page: Page=1, page_size: Size=50) | RecordPage including rejected projection rows; missing version gives 404. |
| compare(db: DB, old_id: str=Query(min_length=1, max_length=36), new_id: str=Query(min_length=1, max_length=36)) | Typed ComparisonView or 404/422; no database writes or network request. |

### backend/app/ingestion/compare.py

| Function and inputs | Output and important logic |
|---|---|
| compare_records(old: list[dict], new: list[dict]) | Deterministic disjoint counts, field deltas and bounded examples; accepted identities only. |
| records_for(db, snapshot_id: str) | List of projected record dictionaries for one bounded snapshot, read from SQL. |
| compare_versions(db, old_id: str, new_id: str) | Comparison dictionary; validates source/scope/policy then adds validation-count deltas. |

### backend/app/ingestion/connector.py

| Function and inputs | Output and important logic |
|---|---|
| parse_rows(lines, max_rows: int) | (rows, headers); exact requested prefix or BatchError, never a silently short success. |
| scope_for(max_rows: int) | Scope dictionary; source-order selection and row limit define comparison compatibility. |
| fixture_batch(path: Path, max_rows: int, max_bytes: int=8000000) | Batch with local-fixture provenance and raw-file SHA-256; bounded file read, same CSV parser. |
| metadata_provenance(meta: dict) | Allowlisted provenance dictionary or BatchError; validates dataset, public access and official CSV URL. |
| CMSConnector.__init__(self, settings: IngestionSettings, transport=None, sleep=time.sleep) | Configured connector; injectable transport/sleep are test seams, not HTTP inputs. |
| CMSConnector.fetch(self) | Complete Batch or safe failure; retries whole bounded downloads and checks release consistency. |
| CMSConnector._metadata(self, client, started) | Bounded JSON provenance; fails on malformed JSON, resource/identifier mismatch or resource bounds. |
| CMSConnector._lines(self, response, started) | Iterator of decoded CSV lines; preserves quoted newlines and checks byte/deadline bounds. |

### backend/app/ingestion/service.py

| Function and inputs | Output and important logic |
|---|---|
| now() | Timezone-aware UTC datetime for audit timestamps. |
| registry_lock(db) | No return value; PostgreSQL transaction-scoped lock with 10-second acquisition timeout, SQLite no-op. |
| ingest(engine, fetch, mode: str, requested: int, before_commit=None) | Run ID; separately commits running audit, then atomic publication or failure audit. Test hook can inject pre-commit failure. |

### backend/app/ingestion/validation.py

| Function and inputs | Output and important logic |
|---|---|
| BatchError.__init__(self, code: str, received: int / None=None) | Configured connector; injectable transport/sleep are test seams, not HTTP inputs. |
| canonical(value) | Canonical JSON string; stable object-key ordering, explicit list order. |
| digest(value) | SHA-256 hex string over canonical JSON; used for scope, identity and content. |
| header_name(value: str) | Normalized column label; strips BOM elsewhere, converts spaces and removes punctuation. |
| validate(rows: list[dict], headers: list[str]) | Validation object with projected rows/findings/counts; rejects duplicate identities after row checks. |

### backend/migrations/versions/002_registry.py

| Function and inputs | Output and important logic |
|---|---|
| upgrade() | Creates only frozen registry tables in migration 002. |
| downgrade() | Drops only registry tables; destructive to registry history, preserves synthetic schema. |

The nested `finding` callback inside validate appends a row finding and marks errors for rejection; warnings do not mark the row invalid. It never logs raw field values. Top-level CLI exception handling sanitizes database/configuration errors; SIGTERM/KeyboardInterrupt uses exit 130. If the database itself is unavailable, no durable audit guarantee is possible.

### Frontend component reference

| Component/helper | Inputs, output and key behavior |
|---|---|
| DataOps | Owns CMS/fixture mode and renders the public-registry shell; mode changes reset Workspace through its key. |
| Workspace | Mode input; requests status/history/attempt pages, owns version selections and inspection IDs; no mutation or network-ingestion action. |
| Compare | Older/newer IDs; requests typed comparison and renders membership bars, caveat and field examples. |
| Records | Version ID; requests projected rows with page size 50 and renders accepted/rejected labels. |
| Findings | Run ID; requests findings with page size 50, distinguishes row numbers from whole-batch findings. |
| CountChart | Named numerical items and accessible label; scales bars to the largest count while keeping explicit text values. |
| Pager | Page/total/size and setter; disables invalid navigation and never requests an unbounded page. |
| Load | Error string; announces loading with status or errors with alert, including migration/health guidance. |
| short / date / statusLabel | Formats IDs, local display dates and the no_change status as Version reused; authoritative IDs/data remain unchanged. |

All existing synthetic views remain in App.tsx. Only navigation and page-specific labels were extended. styles.css adds wrapping/overflow styling for commands, checksums, actions and provenance. The existing API race guard remains byte-identical.

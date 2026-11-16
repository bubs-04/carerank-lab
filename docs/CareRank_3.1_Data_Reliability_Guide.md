# CareRank 3.1 — Data Reliability Guide

For Prabhat Mattaparthi. Built on the exact CareRank 3.0 source archive at commit 351d714. This guide progresses from everyday ideas to implementation and verification. It accompanies the Word document of the same name.

## 1. Begin with the delivery, not the technology

Imagine a supplier sends a spreadsheet every morning. Yesterday it had five usable rows. Today two rows repeat the same identity, some cities are blank, or the download stops halfway through. A data engineer needs to know what arrived, whether processing finished, and which changes deserve investigation.

Data ingestion is the process that retrieves and stores that delivery. Data-quality monitoring inspects the resulting evidence. CareRank 3.0 already ingests bounded public CMS provider records and retains snapshots. Version 3.1 adds rules, alerts and an investigation history around those records. It does not evaluate patient outcomes or identify better clinicians.

A provider can have multiple enrollment/practice-location records. The source identity is the existing NPI + enrollment ID + optional group PAC ID + address ID. Duplicate identity is a repeated complete source key, not merely two rows sharing an NPI. CMS identities remain separate from the fictional ranking providers and scores.

Read first: README, RULES_3.1.md, monitoring/rules.py, monitoring/service.py, then Monitoring.tsx. Follow one example end to end before reading every framework file.

## 2. Follow a five-row example

The existing artificial fixture contains five rows. Four are accepted, one has an invalid identifier, and one accepted row lacks specialty, city and state. That produces three warning findings, not three additional rejected records. At the default thresholds, rejection is 1/5 = 20%, and each missing-field rate is also 1/5 = 20%. Those four rules fail their 5% thresholds and create four warning alerts.

The first run has no comparable earlier success. Its five change rules are not evaluable. That is useful information: the system is honest about the missing baseline. It does not pretend that missing history means no change.

Ingest fixture B next. Existing comparison logic identifies one added identity, one removed identity, one changed shared identity and two unchanged identities. The union has five identities, so each change proportion is 20%. The default change threshold is greater than 25%; those checks pass. The same four missing/rejected alerts are still generated for this new attempt. Repeating evaluation of that attempt creates none. Repeating ingestion creates a separate attempt, even when it reuses an existing snapshot.

## 3. Understand a rule and its three outcomes

A rule is a small, explainable question: is the observed percentage greater than a configured threshold? The rule stores an ID, description, algorithm version, severity, threshold and measurement unit. The evaluation stores the observation, status, evidence, run, snapshot and baseline.

Passed means observation <= threshold. Failed means observation > threshold. Not evaluable means the necessary evidence is unavailable. Exactly 5% passes a rule configured to alert above 5%; 5.01% fails. No amount of rounding in the display changes the stored decision.

A threshold is a review trigger, not a theorem about bad data. A legitimate new source release, an unusually small sample, or a source reordering can trip a rule. That is a false positive if an engineer expected the change and the data is valid for its purpose. A generous threshold can also miss an important small change. Start with transparent rules, examine incidents, and adjust thresholds with recorded versions rather than inventing statistical confidence from two examples.

The full twelve-rule table, units, defaults and environment names are in RULES_3.1.md. Warning findings per 100 rows are not a percentage of defective rows; one row can have several warnings. Comparison proportions use a shared union denominator. Keeping denominators explicit prevents misleading totals.

## 4. Select a baseline you can defend

The engine looks for the most recent successful attempt that finished before the current one began, with the same source ID, scope hash and validation policy. A scope describes the prefix-selection method, row bound and selected fields. An overlapping attempt is not used as an earlier baseline. Live and fixture sources stay separate.

This is deterministic anomaly detection: given the same stored run, prior history and rule profile, it makes the same decision. There is no machine-learning model, training phase, probability, confidence interval or requirement for a live network during tests.

The CMS connector retrieves the first bounded group of source rows. If the publisher inserts one row near the top, another may fall beyond the cutoff. The comparison may say added/removed even though neither clinician's actual Medicare status changed. An address-key change and a rejected row can also alter accepted membership. The UI presents these as sample-relative investigation signals.

One prior compatible run is sufficient to calculate a difference, but not to establish normal statistical variation. With no compatible prior run, five rules stay not evaluable. The trend chart includes compatible successful attempts only; failed attempts are visible in history and alerts, not silently represented as zero rows.

## 5. See how the pieces work together

The ingestion CLI retrieves CMS data or a clearly labeled offline fixture, validates it, and commits a registry attempt/snapshot using the existing 3.0 architecture. After that commit, the monitoring hook opens a separate transaction and evaluates the completed attempt. An error in monitoring cannot undo the successful data delivery.

FastAPI exposes JSON through read-only REST endpoints. REST here means the browser makes HTTP requests for resources such as alerts or evaluations. React's useApi hook requests those resources, handles loading/errors, and ignores aborted/stale responses. React renders tables, semantic bar charts and an SVG trend. PostgreSQL holds the durable facts; the browser does not download encounters or calculate clinical scores.

The architecture image in the Word guide is a schematic, not a website screenshot. No new browser screenshots were captured because Chrome failed before page navigation in this environment. Existing screenshots/documents remain historical evidence, not proof of the 3.1 UI.

## 6. Learn the four new tables

| Table | What it stores | Why it exists |
|---|---|---|
| monitor_rules | Content-addressed rule definitions, versions and thresholds | Preserve exactly which rule made a decision |
| monitor_evaluations | Run/profile/rule result, observation, evidence and baseline | Keep passed and unavailable checks as well as failures |
| monitor_alerts | Current incident state, severity, assignment, revision and resolution | Give an engineer a durable object to investigate |
| monitor_events | Creation and every subsequent decision with actor label and revision | Explain how the incident state changed over time |

Foreign keys connect these tables to existing registry runs and snapshots; they do not connect to synthetic provider scores. The migration follows 002 as revision 003. It adds tables and indexes without changing old rows. Unique constraints protect one evaluation per run/profile/rule and one alert per run/rule version. Indexes support run, profile, status and severity queries.

Rule content is hashed with SHA-256. A changed threshold produces a different rule configuration ID. The profile hashes all current rule configuration IDs. Old evaluations remain available under historical configurations. A hash here is a stable identity, not proof that an operator is authenticated or that data is confidential.

## 7. Transactions prevent half an investigation

A transaction groups changes into one commit. In evaluate_run, the engine takes a short write lock, loads the completed run, checks for existing results, registers definitions, derives metrics, writes all twelve evaluations, and adds any new alerts plus their creation events. A test can inject failure just before commit. If it does, none of those new monitoring rows should remain.

The investigation transaction verifies the expected alert revision, validates a state transition, updates the alert and appends an event. If a second operator used an older revision, the command fails without changing either the alert or its history. This avoids silently overwriting another person's decision.

PostgreSQL uses a transaction-scoped advisory lock for short monitoring writes. This implementation serializes them deliberately; it does not claim high-throughput benchmarking. A unique database constraint is an additional safeguard. SQLite tests use BEGIN IMMEDIATE for their own concurrency exercise; they cannot prove PostgreSQL behavior. Separate PostgreSQL tests exist for the supported local/CI environment.

The migration installs an audit trigger rejecting UPDATE and DELETE on events. The CLI exposes append actions only. A database administrator with sufficient privileges could still alter the schema, so this is not a cryptographically tamper-proof ledger. Proper production authentication, separate read/write database roles and managed audit retention remain future work.

## 8. Investigate an alert safely

An alert begins open. You may acknowledge it or begin investigating. Acknowledged can become investigating or resolved; investigating can become acknowledged or resolved. Resolved can reopen as open. Open cannot jump straight to resolved. Every action requires a meaningful note and the current revision.

Assignment is an optional local label. A note without a status change is still an audit event. Resolving stores the note in the current resolution field; reopening clears that field while retaining the historical resolution event. Re-evaluating data does not silently close incidents or rewrite their evidence.

There are no authenticated user accounts in this app. Allowing arbitrary browser visitors to modify alerts would create a security problem. The dashboard therefore uses GET only, and trusted local operators use the CLI. The --actor value is self-reported; HTTP headers such as X-User are ignored. Never describe that label as verified identity.

Use inspect first, then investigate with the actual alert ID, expected revision, actor and note. API_3.1.md includes exact commands. Keep notes about technical evidence; do not put private patient information or credentials into them.

## 9. Walk through the dashboard

Data Operations retains its source-mode selector and Refresh status button. Choose Ingestion and versions for the existing registry workflow, or Quality monitoring for reliability. Refresh remounts the selected workspace without navigating away or changing CMS/fixture mode. Mobile navigation and the useApi race-condition protection from the supplied baseline remain intact.

The health panel explains no data, disabled, pending, attention, partial or passed. Only passed is green, and only after all current rules passed for the latest attempt with no unresolved alerts. A bar chart separates passed, failed and unavailable rule results. Another shows unresolved alerts by severity. Zero alerts alone is explicitly not proof of a pass.

Alert history filters by status and severity and loads one bounded page at a time. Inspect evidence opens the original rule, threshold, observation, count evidence and audit events. View attempt and findings opens the exact run and existing findings panel. View snapshot records opens captured source rows. Baseline findings links to the comparison reference.

The evaluation section can select a recent attempt and include historical configurations. Each expandable result shows raw reproducible evidence. The trend-reference selector changes the compatible cohort; the chart and exact-value table show accepted counts across up to twenty successful retrievals. A single observation does not draw a misleading line. Loading, error and empty states describe the missing evidence.

## 10. Understand failures and recovery

The existing connector retains its timeouts, bounded retries and interrupted-download handling. This release does not add a new external data fetch. Ordinary failed/interrupted attempts are evaluated after their durable audit is committed. Source-contract errors can create a critical alert even when there is no snapshot; the other missing measurements remain unavailable.

If monitoring itself fails, ingestion remains committed and a structured monitoring_pending log identifies the run and safe exception class. The dashboard shows pending current-profile coverage. Fix the database/configuration issue and run the bounded evaluation backfill; reruns are safe.

A hard process kill cannot execute cleanup code. A run can remain running until an operator confirms the worker stopped and uses the existing mark-interrupted command. There is no background scheduler, job lease or automatic stuck-worker timeout in this release. The API never guesses that a running job has completed.

## 11. Make and test a small change

Start with a copy of the feature branch and read one component. For a safe UI change, edit the explanatory text beside Comparable retrieval trends in frontend/src/Monitoring.tsx. Run the frontend development server against your local API using the repository's existing instructions. Saving the file updates the browser through Vite. Run npm test and npm run build afterward.

For a backend exercise, change a threshold in a test's MonitoringSettings object instead of editing your production-like .env. Run that targeted pytest case and inspect both stored configurations. If changing rule semantics, increment the rule algorithm version and add a test that demonstrates why the old decision differs. Keep snapshot records and old evaluations unchanged.

Use the five exercises and two-minute demo script alongside this guide. Explain your prediction before running a test, then state what the result actually proves. A browser DOM test does not prove PostgreSQL locks; a SQLite rollback does not prove PostgreSQL migrations; a build does not prove the website was visually inspected.

## 12. Explain the engineering in an interview

A healthcare analytics organization needs confidence in source feeds before using them downstream. This subsystem gives source lineage, repeatable rules, incident context and an auditable investigation process. Its contribution is operational reliability around provider registry data, not a clinical ranking method or a claim about Garner's systems.

Describe a concrete failure: an interrupted download has unknown validation rates, so the engine records an attempt failure and refuses to show green completeness checks. Describe a tradeoff: a global short advisory lock is simple and safe for the bounded workload, but would need measurement before scaling. Describe a security boundary: no unauthenticated mutation API, with local CLI investigation until authentication is deliberately added.

Be candid that AI assisted implementation, tests and documentation. Your understanding should come from tracing the five-row example, running the checks, changing one rule and defending its denominator. The verification report separates what actually ran from checks waiting for a supported PostgreSQL/browser environment.

## 13. Important function reference

The following function inventory is generated from the shipped source and paired with purpose, inputs and outputs. Read the implementation together with its test rather than memorizing names.

| Function | Inputs | Output | Important logic |
|---|---|---|---|
| __main__.py::main | Parsed local command-line arguments | JSON results and process exit status | Dispatches bounded missing-profile backfill, inspection or investigation; never exposes a write route. |
| api.py::current_profile | Environment settings | Settings, definitions and profile hash | Converts invalid monitoring configuration into a sanitized 503 response. |
| api.py::evaluation_view | Session and Evaluation row | Typed API-ready evaluation plus stored rule | Attaches the original definition so historical thresholds are explainable. |
| api.py::summary | Session and source mode | Health, latest run, counts and explanation | Green requires complete current coverage, all passed, and no unresolved alerts in that mode. |
| api.py::rules | Current environment | Current rule-definition list | Shows configured rules even before a run has been evaluated; does not write them. |
| api.py::run_detail | Run ID and session | Exact registry run or 404 | Links investigation to the underlying recorded attempt. |
| api.py::evaluations | Mode, run filter, profile filter and page | Bounded evaluation page | Defaults to current profile; optional historical configurations remain visible. |
| api.py::alerts | Mode, severity/status filters and page | Bounded alert page | SQL filters and stable ordering; no write action. |
| api.py::alert_detail | Alert ID and session | Alert plus originating evaluation or 404 | Preserves the evidence that created the incident. |
| api.py::events | Alert ID and page | Audit events ordered by newest revision | Pagination avoids fetching unbounded history in the browser. |
| api.py::trends | Mode, optional successful reference run, bounded limit | Compatible run points, scope, policy and caveat | Filters source/scope/policy; excludes failed attempts and future starts relative to reference. |
| rules.py::definitions | MonitoringSettings | Ordered list of twelve Rule objects | Names each measurement, unit, default severity and semantic algorithm version. |
| rules.py::profile_id | List of Rule objects | SHA-256 profile ID | Hashes sorted definition IDs so evaluation coverage refers to a concrete rule set. |
| rules.py::decide | Rule, observation or None, evidence, reason | Status/observation/explanation/evidence dictionary | Uses > for failure; None becomes not_evaluable with an explanation. |
| rules.py::id | Rule dataclass fields | SHA-256 configuration ID | Hashes the full definition, including threshold; changing it preserves old definitions. |
| service.py::lock | Database session | Transaction-scoped write lock | PostgreSQL advisory lock 721306 with timeout; SQLite BEGIN IMMEDIATE for portable tests. |
| service.py::baseline_for | Session, current run, snapshot | Prior compatible run or None | Matches source, scope and policy; prior completion must precede current start. |
| service.py::measurements | Session and completed run | Observed metrics, evidence, baseline ID | Checks complete publication, aggregates distinct finding rows in SQL, then calls existing bounded snapshot comparison. |
| service.py::evaluate_run | Engine, run ID, optional settings and fault hook | Profile/result-count summary or pending status | One transaction creates all results and new alerts/events; repeated profiles are reused; unchanged rule alerts deduplicate across profiles. |
| service.py::evaluate_safely | Engine and completed run ID | Post-commit evaluation or safe pending log | Honors automatic enable setting and isolates monitoring errors from ingestion success. |
| service.py::investigate | Engine, alert, actor, note, expected revision, optional state/assignee | New status and revision | Validates limits and lifecycle, prevents stale writes, appends the decision atomically. |

The request handlers delegate SQL pagination to the existing ingestion.api.paged helper. Schema classes validate the response shape; they contain no mutation logic. MonitoringSettings validates finite thresholds and supplies environment defaults. ORM classes map the four monitoring tables described above.

| React component / integration point | Inputs | Output and behavior |
|---|---|---|
| Monitoring | Source mode and evidence-navigation callback | Owns filters, pages, selected alert and trend reference; renders the read-only reliability workspace. |
| Loading | Error string | Accessible loading status or actionable error; never displays success on failure. |
| Pager | Current page, total, update callback | Bounded Previous/Next controls with disabled limits. |
| Bars | Named counts and chart title | Semantic horizontal bars with exact labels/counts; used for evaluation outcomes and unresolved severity. |
| Evidence | Evaluation and navigation callback | Shows threshold, original rule, observation, raw evidence, attempt/snapshot/baseline links. |
| AlertInvestigation | Alert ID and navigation callback | Loads alert/evaluation and a paginated audit history; offers local CLI instructions only. |
| Trends | Mode and successful reference run | Loads compatible points, draws accepted-count SVG with a zero baseline and a full data table; single point has no inferred trend. |
| DataOps (existing, extended) | Source mode, refresh key, selected area and evidence selection | Keeps refresh/source behavior; switches between original ingestion workspace and monitoring. |
| Workspace (existing, extended) | Mode and selected run/snapshot context | Preserves existing ingestion/version/comparison controls; opens evidence selected from monitoring. |
| Attempt (new helper in DataOps) | Run ID | Fetches and displays the exact attempted delivery instead of confusing it with the latest run. |
| useApi (unchanged) | Endpoint URL | Aborts obsolete requests and guards stale response updates; reused for every monitoring resource. |
| ingestion.service.ingest (existing, extended) | Existing engine, fetch function, mode, row bound | Calls monitoring only after the original success/failure transaction commits; original source validation and publication remain unchanged. |
| ingestion CLI main (existing, extended) | Existing mark-interrupted command | Evaluates an explicitly completed interrupted attempt after committing that status. |
| migration 003 upgrade | Alembic database connection | Creates four new tables and an event-update/delete guard; references old tables without altering them. |
| migration 003 downgrade | Alembic database connection | Drops monitoring tables and PostgreSQL trigger function; loses monitoring history but leaves registry and synthetic tables intact. |

## 14. References and verification boundaries

Project-specific sources of truth are the shipped source, RULES_3.1.md, API_3.1.md and VERIFICATION_3.1.md. Official documentation consulted for transaction/migration behavior:

- PostgreSQL explicit locking: https://www.postgresql.org/docs/current/explicit-locking.html
- SQLAlchemy 2.0 session transactions: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- Alembic migrations tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html

These references explain framework behavior; they do not establish that this environment executed PostgreSQL tests. The code retains the repository's pinned dependencies. Use the upgrade guide to validate your actual database and browser before presenting those checks as passed.

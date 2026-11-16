# Two-minute engineering demo

Prepare: upgrade to 003, run fixture A then B from the upgrade guide, open Data Operations → deterministic fixture mode → Quality monitoring. Have one alert ID ready. Every demonstration record is artificial; do not describe these fixtures as real CMS retrievals.

**0:00–0:20 — Problem and boundary**

“CareRank separates its fictional ranking experiment from a public provider registry. Version 3.0 captured bounded CMS source snapshots. In 3.1 I added monitoring to help an engineer ask whether a delivery completed, which rules failed, and what evidence explains the result. These fixture records let me demonstrate failures reproducibly without depending on a live network.”

**0:20–0:45 — Health with evidence**

Show latest-attempt outcomes and unresolved alerts.

“There are twelve deterministic rules. Passed, failed and not evaluable are separate outcomes. A first ingestion has no compatible baseline, so the change rules cannot pass yet. An incomplete download also cannot masquerade as zero rejected records. Green means every current rule passed for the latest attempt and no alerts remain unresolved.”

**0:45–1:10 — Explain one alert**

Open a missing-specialty or rejection alert and expand its evidence.

“This rule stores its threshold, observed percentage, numerator and denominator, source scope, rule version and related run. Repeating the same evaluation reuses its result and does not duplicate this alert. A changed threshold produces a new configuration while preserving the original decision.”

**1:10–1:35 — Investigation and transactions**

Show the CLI command and investigation history; optionally execute a prepared investigating transition with the current revision.

“The app has no user authentication, so I kept writes in a local operator CLI. The dashboard is read-only. Each decision checks the current revision, updates the alert and appends an audit event in one transaction. PostgreSQL constraints and locking protect concurrent evaluation; audit triggers reject edits and deletion of events. Names are self-reported operator labels, not verified accounts.”

**1:35–2:00 — Scope and engineering judgment**

Show the comparable-retrieval trend or comparison evidence, then the verification report.

“Baselines require the same source, scope and validation policy. The CMS connector retrieves a bounded prefix; a row crossing its cutoff is not proof that a clinician entered or left Medicare. I chose transparent thresholds before machine learning and wrote offline tests for boundaries, rollback, deduplication and conflicts. The report separates executed checks from the PostgreSQL and browser checks still needing a supported environment.”

If you have since run the local PostgreSQL/browser checks successfully, show your actual output and update the report before claiming those passes. This is an independent portfolio project, with no Garner or CMS affiliation and no clinical conclusions.

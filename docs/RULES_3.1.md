# Monitoring rules, versions and limitations

Twelve deterministic rules use **strictly greater than** comparisons. Equality passes. Defaults are review triggers chosen for a portfolio application, not statistically calibrated thresholds. All percentage denominators are explicit. No patient outcomes or clinician quality are inferred.

| Rule ID | Measurement | Default threshold | Severity | Configuration |
|---|---|---|---|---|
| attempt_failure | 1 for a completed failed/interrupted attempt, otherwise 0 | > 0 | critical | Fixed definition |
| source_contract | Recorded schema/provenance finding count, including new-column warnings | > 0 | critical | Fixed definition |
| rejected_rate | Rejected rows / received rows × 100 | > 5% | warning | DQ_REJECTED_PERCENT |
| duplicate_rate | Distinct row numbers with duplicate_identity / received × 100 | > 1% | critical | DQ_DUPLICATE_PERCENT |
| missing_pri_spec | Distinct rows with missing_optional on pri_spec / received × 100 | > 5% | warning | DQ_MISSING_PERCENT |
| missing_citytown | Same, citytown | > 5% | warning | DQ_MISSING_PERCENT |
| missing_state | Same, state | > 5% | warning | DQ_MISSING_PERCENT |
| warning_change | Absolute difference in warning findings per 100 received rows | > 10 findings/100 rows | warning | DQ_WARNING_RATE_CHANGE |
| accepted_change | Absolute change in accepted count / previous accepted count × 100 | > 20% | warning | DQ_ACCEPTED_CHANGE_PERCENT |
| added_rate | Added accepted identities / union of both accepted identity sets × 100 | > 25% | warning | DQ_MEMBERSHIP_PERCENT |
| removed_rate | Removed accepted identities / same union × 100 | > 25% | warning | DQ_MEMBERSHIP_PERCENT |
| changed_rate | Changed shared identities / same union × 100 | > 25% | warning | DQ_MEMBERSHIP_PERCENT |

The union is added + removed + changed + unchanged. These three change proportions share a denominator and do not overlap. A row can have several missing-field findings; those rates are separate rules and must not be summed into a rejected-record total. Duplicate rate counts every row involved in a duplicate identity, not only excess copies. Warning counts count findings, not rejected rows, and can exceed the row count.

Snapshot rules require a successful/no-change completed run, exact requested/received equality, matching run/snapshot counts, matching source, and the expected number of stored rows. A failed run with partial counts still cannot pass completeness rules. Recorded source errors can fail independently of completion; if a download failed before source verification, absence of a source error is not proof of a valid source and that rule is not evaluable.

Source-contract signals include codes beginning `schema_` or `metadata_`, `source_changed_during_download`, and `new_column`. Treating an unknown column warning as a critical contract-review signal is deliberately conservative; it does not relabel that original finding as an error. Optional missing release dates do not generate invented provenance errors. Other HTTP/download errors are captured by attempt_failure.

## Context and baseline

The baseline is the latest successful/no-change run that finished **before the current attempt started**, with the same source ID, scope hash and validation policy. Scope includes selected fields, prefix selection method and requested row limit. Overlapping attempts do not establish an earlier baseline. Ties use run ID for deterministic ordering. Reused or reverted versions still have distinct attempts and may be valid baselines.

There must be at least one compatible prior success for five change rules. One prior run supports a deterministic difference, not a statistical anomaly model. No standard deviations, confidence intervals, national trends or population claims are made. A 1,000-row prefix cannot be compared to a 5,000-row prefix. Live CMS and artificial fixtures never share baselines.

CMS may reorder rows near the prefix cutoff. An added/removed record may reflect that boundary, a changed address identity, or rejection of a row. It does not establish that a clinician joined or left Medicare. Trends deliberately plot only compatible successful retrievals; failed attempts remain visible in attempt history and alerts.

## Versioning and configuration

Each definition has algorithm version 1.0 and a SHA-256 identifier over its ID, description, severity, threshold, unit and version. A profile hashes the ordered set of definition identifiers. Changing a threshold creates new persisted definitions/evaluations without rewriting past evidence. The dashboard uses the API process's current configuration; keep CLI and API DQ variables consistent. No new runtime dependency is required.

Compose forwards optional DQ variables and supplies defaults; existing `.env` files need no edits. For a temporary experiment, export a variable before both the evaluation command and API recreation, or pass `-e` only to a deliberate historical-profile evaluation and view historical configurations. Restore the default environment afterward. Percentage rates reject values outside 0–100; count-change settings allow nonnegative finite values because relative changes can exceed 100%. NaN and infinity are invalid.

There is no scheduler or automatic stale-worker detector. Normal exceptions and termination signals record completed failures/interruption and evaluate them. After an uncatchable kill, a run can remain running. Confirm the worker has stopped, then use the existing `app.ingestion --mark-interrupted RUN_UUID`; 3.1 evaluates that completion. If the database is unavailable, evaluation/failure audit can remain pending. Use the backfill command after recovery. Monitoring failure is logged as structured `monitoring_pending` with run ID and safe exception type.

Threshold alerts persist until reviewed. New successful data does not erase older incidents. This release does not send email, Slack, or other external notifications.

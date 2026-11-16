# Two-minute engineering demonstration

Before presenting: apply migration 002, run the two fixture CLI commands, run a bounded live CMS job if your network permits, and verify the local UI. Do not substitute fixtures for claimed live results. Keep your terminal free of credentials.

**0:00–0:20 — Source and separation**

“CareRank now has a public provider registry alongside its synthetic ranking lab. These systems are deliberately separate: no CMS identity receives a fictional clinical score. The registry uses the official Doctors and Clinicians National Downloadable File.”

Open Data operations in Live CMS mode. Show latest attempt and last successful retrieval.

**0:20–0:45 — Arrival and provenance**

“The CLI discovers the CSV through CMS metadata and streams a bounded prefix. This run records its release, retrieval time, counts and selected-content checksum. Each source row is a clinician/enrollment/group/address combination, so several rows can belong to one NPI.”

Open source provenance and inspect a captured version. Mention that a 1,000-row sample is not a national census.

**0:45–1:10 — Trust and failure handling**

Switch to the clearly labeled fixture mode and show findings.

“Fixtures make failures reproducible without depending on CMS in CI. Missing optional specialty values create warnings. Invalid identifiers are rejected, and duplicate identities reject every occurrence. Findings explain each decision; warnings are not counted as extra rejected records.”

**1:10–1:35 — Versions and comparisons**

Select fixture A as older and B as newer.

“This example has one added, one removed, one changed and two unchanged accepted records. The changed record has a specialty and city difference. A changed address key appears as removal/addition. Because these are bounded captures, I do not claim national clinician exits.”

**1:35–2:00 — Transactions, idempotency and verification**

“The attempt audit commits first. Snapshot rows, findings, comparison summary and success status publish atomically. Failure preserves the last good snapshot. Matching content reuses a version; PostgreSQL locking and a unique constraint protect concurrent commits. The delivery ran real CMS ingestion twice in isolated SQLite and retained one version. PostgreSQL concurrency and browser checks still need the supported local environment. AI assisted implementation; I can trace each chart to its query and tests.”

Update the final verification sentence only after actually running the outstanding checks. Use `EXERCISES_3.0.md` to practice before claiming independent ownership of the implementation.

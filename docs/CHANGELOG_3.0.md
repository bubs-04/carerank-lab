# CareRank 3.0 technical changelog

- Extended the delivered 2.0 source in an isolated workspace on a local `feat/cms-data-ingestion` branch. Private remote access was unavailable; no remote branch was read, pushed or merged.
- Added official CMS metadata discovery and a bounded streaming CSV connector, with origin/path checks, release consistency checks, timeouts, decoded-byte/deadline limits, retry/backoff and safe errors.
- Added a reusable validation layer and explicit clinician/enrollment/group/address identity. Multiple source records per NPI are preserved. Only seven selected registry fields are retained.
- Added migration 002 and six independent registry tables for sources, runs, snapshots, source rows, findings and stored comparison summaries. No foreign keys link registry identities to synthetic scores.
- Added durable attempt audits, atomic publication, content/scope/policy uniqueness, PostgreSQL advisory locks and database constraints. Reused or reverted content retains version identity; ordered capture hashing keeps row-level findings aligned.
- Added reproducible accepted-record comparisons with exact field differences, specialty/location counts, validation deltas and sample-boundary caveats.
- Added a CLI for live or explicitly labeled fixture ingestion and interrupted-run recovery. No HTTP write/trigger endpoint exists.
- Added six typed read-only DataOps routes, bounded pagination and generated OpenAPI documentation.
- Added Data Operations navigation, separate CMS/fixture modes, job health, version/run history, record inspection, findings, validation charts and comparison charts. Corrected page-specific wording so real registry data is not labeled synthetic.
- Added 39 portable ingestion checks, two PostgreSQL-specific checks, seven frontend checks, an optional live test and an opt-in DataOps browser workflow. Existing tests remain.
- Extended existing CI with offline fixture CLI ingestion and DataOps screenshot artifact paths. CMS network is not required by default CI.
- Added architecture, API/validation documentation, Word learning guide, function catalog, demo script, five exercises, exact file manifest, verification evidence, safe Mac upgrade and review/commit instructions.

Preserved: synthetic generator, scoring, pipeline, schema/models, original migration 001, prior APIs, 2.0 analytics, useApi race fix, Compose, Dockerfiles and dependency lockfiles. Application version is 3.0.0; no new application runtime dependency was added.

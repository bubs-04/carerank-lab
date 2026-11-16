# CareRank 3.1 technical changelog

Baseline: uploaded Git archive comment `351d7143b49b3f2e151d6877d0074ef050d53a60`; target branch `feat/data-quality-monitoring`. Private GitHub authentication was unavailable. The patch is against the exact source bytes in that archive, including the 3.0 mobile navigation and Refresh status fixes. No push, merge, deployment, or visibility change occurred.

- Added 12 deterministic, versioned monitoring rules with configurable thresholds, explicit units, evidence and pass/fail/not-evaluable results.
- Added compatible-baseline selection using source/scope/validation policy and non-overlapping attempt times; documented bounded-prefix changes and sparse-history limitations.
- Added migration 003 with four isolated monitoring tables: immutable rule definitions by content identity, evaluations, durable alerts and append-only investigation events. Foreign keys reference existing registry history only.
- Added transactional evaluations and PostgreSQL advisory locking, uniqueness constraints and repeat-safe profile evaluation. Alerts deduplicate per attempt/rule version even when an unrelated profile setting changes.
- Added automatic post-commit evaluation for ingestion successes, reused versions, ordinary failures, interruption and operator-marked interrupted attempts. Monitoring failure preserves ingestion results and can be backfilled.
- Added a local CLI for bounded backfill, explicit run evaluation, inspection, notes, assignment and lifecycle transitions, protected by expected revision checks. No public write API or header-derived actor identity was added.
- Added eight typed read-only endpoints and generated OpenAPI documentation.
- Extended Data Operations with monitoring health, evaluation-outcome and severity charts, filtered/paginated alert history, evidence, audit history, comparable retrieval trends and links into existing finding/record panels.
- Preserved Refresh status behavior, source mode, mobile navigation, useApi abort/race protection, ranking, comparisons and analytics. Kept the lightweight semantic HTML/SVG chart approach.
- Added deterministic backend/React/Playwright and opt-in PostgreSQL tests. CI remains independent of the live CMS network; browser artifacts now include monitoring views when tests can execute.
- Added optional Compose environment forwarding; existing credentials, volume definitions, service dependencies and synthetic seed behavior remain unchanged.
- Added the learning guide, rule specification, API guide, architecture diagram, upgrade/rollback procedure, demo, exercises, exact file inventory and verification evidence.

No scoring weights, model assumptions, synthetic generator, CMS record identity, connector, validation policy or snapshot comparison algorithm changed. Defaults still seed 1,000 fictional providers and 100,000 encounters only on the existing fresh-install path. Upgrades must use the no-seed procedure.

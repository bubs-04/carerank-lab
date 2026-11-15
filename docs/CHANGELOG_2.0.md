# CareRank Lab 2.0 changelog

- Added read-only `/api/analytics/quality-cost` and `/api/analytics/evidence` endpoints with explicit Pydantic response models and OpenAPI descriptions.
- Added SQL cohort means and all-eligible-provider projections, independent of paginated provider search.
- Added disjoint evidence categories, exact completeness bins, and explicit zero-encounter/missing-materialization handling.
- Added Analytics navigation and an Overview shortcut; clarified the Overview eligibility card's two thresholds.
- Added an interactive SVG scatter with specialty filtering, strict mean-based highlighting, hover/focus information, keyboard profile navigation, and a complete data-table alternative.
- Added specialty eligibility stacks and a completeness histogram with numerical counts, category definitions and accessible summaries.
- Added grouped comparison bars with fixed 0–100 component scales, weights, provider legends, precise numerical tables, weighted contributions and interpretation guidance. Existing profile details remain.
- Added responsive analytics styles; no chart dependency or architecture replacement.
- Added 8 portable SQL/API tests and 8 frontend tests. Added a PostgreSQL integration test and a second Playwright workflow for analytics, mobile layout and keyboard navigation. CI now retains analytics screenshots.
- Updated README, safe Mac upgrade guide, verification report, screenshot procedure, two-minute demo script and a new Word engineering walkthrough.
- Preserved generator, pipeline, scoring weights/formulas, schema, migrations, Compose, Dockerfiles, lockfile and the prior async-response race fix. API version is now 2.0.0.

Verification: 28 backend checks passed; 14 PostgreSQL tests skipped without a disposable database. 13 frontend checks passed; 1 optional live test skipped. Production build and formatting passed. Docker engine was unavailable and browser launch failed before navigation; no new screenshots or end-to-end pass claimed. See `VERIFICATION_2.0.md` for exact boundaries.

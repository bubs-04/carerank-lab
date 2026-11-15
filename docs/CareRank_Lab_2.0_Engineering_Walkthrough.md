# CareRank Lab 2.0 — Engineering Walkthrough

Prabhat Mattaparthi · Independent engineering portfolio · 15 November 2026

Synthetic data only. No clinical recommendations. Not affiliated with Garner.

## 1. Start with the question, not the technology

Imagine a table of fictional doctors and scores. You can sort it, but it does not explain whether the expensive providers also have higher scores, whether a score rests on enough observations, or why two providers differ. CareRank Lab 2.0 adds three ways to investigate those questions without changing the score itself.

The Quality vs. Cost Explorer places every eligible provider in one selected specialty on a plot. The Comparison view separates a final score into its four components. The Evidence dashboard shows who can be ranked and who lacks evidence. These are views of the same stored snapshot, not new prediction models.

This is an extension of the existing React → FastAPI → PostgreSQL application. The original generator, pipeline, schema, migrations, Docker setup and scoring rules remain intact. No database migration is needed. The latest frontend race-condition guard is retained byte-for-byte.

Read this progressively: first use the charts, then trace a point to an API response, then inspect the SQL and tests. The older Beginner's Guide still explains the original pages and technologies; this walkthrough focuses on the upgrade.

## 2. Walk through the product

### Overview

The existing provider, encounter, eligibility and mean-score cards remain. The eligibility card now states both requirements: at least 30 observed outcomes and at least 80% completeness. Explore providers opens the existing search page. Explore analytics opens the new Analytics page. The pipeline status still describes the existing data refresh.

### Analytics — quality versus cost

The Comparable specialty selector defaults to Cardiology. It offers specialties returned by the existing metadata endpoint; there is no mixed-specialty option. Changing it requests the complete eligible cohort for that specialty, independent of the Explorer's filters, sorting or page number.

Each point is one provider. X is raw average synthetic encounter cost in dollars. Y is the stored simulated quality score, from 0 to 100. Hover or focus a point to see the provider's name, precise displayed score and cost. Clicking it, pressing Enter or Space opens the existing provider profile. A native tooltip and a visible information area provide the same basic facts.

Dashed lines are arithmetic cohort means. A diamond means score strictly above the cohort mean AND raw cost strictly below the cohort mean. Equality is not highlighted. Other eligible providers are circles. For example, if the cohort means are $150 and 60, a fictional provider at $100 and 70 is highlighted; one at $150 and 70 is not. This is an illustration, not a measured result from your dataset.

These means describe only eligible providers in the selected specialty. They are sensitive to outliers and are not clinical targets, confidence bounds or a Pareto frontier. Higher heuristic scores and lower raw costs do not establish clinical superiority. The scoring cost component is normalized; the scatter's raw cost is deliberately different and labeled accordingly.

The expandable data table contains every plotted provider, including those hidden behind overlapping points. It is an accessible alternative and a more precise way to compare numbers. Its provider buttons open the same profiles. No points are sampled or limited to the 12-row search page.

### Analytics — evidence

The specialty bars show the proportion in each category, with numerical counts. The category totals account for every provider once. Below the bars, an expandable table exposes exact counts by specialty.

The completeness histogram counts providers by observed outcomes divided by encounter count. It does not count successful outcomes. A provider with 100 outcomes recorded and only 50 successes has 100% completeness; that is different from a 50% success rate.

No encounters has undefined completeness and its own bin. Not processed indicates no materialized score row. For exclusion reasons, insufficient observed outcomes takes precedence when both eligibility tests fail. This avoids adding overlapping exclusion counts together.

### Provider Explorer and Profile

Search, filters, sorting, pagination, selection and profiles retain their existing behavior. Selecting providers from different specialties remains invalid. Profiles retain raw counts, cost, completeness, shrinkage, residual, normalized cost ratio and the detailed component breakdown. Chart clicks open this same profile implementation, rather than a second copy.

### Comparison

Select two or three providers in one specialty and press Compare. The new grouped horizontal bars show the same four unweighted components on a common 0–100 scale. Provider names and colors form the legend; each bar also has a name and numeric value, so interpretation does not depend on color alone.

The accompanying table shows component → weighted points. An outcome value of 50 contributes 30 points because 50 × 60% = 30. A cost value of 60 contributes 15 points because 60 × 25% = 15. Ten more outcome-component points add six final-score points; ten more cost-component points add 2.5.

An unscored provider may still have descriptive components. Its legend explicitly says unscored, and the original profile displays insufficient data rather than a zero score. No new rank is invented. Components are rounded when stored, so summing displayed weighted values may differ slightly from the stored final score calculated before component display rounding.

## 3. Follow one fictional encounter

Consider an illustrative encounter with risk 0.5, outcome 1 and cost $150 for a consultation with a procedure multiplier of 1. The known simulation baseline predicts 0.95 − 0.30 × 0.5 = 0.80 success. This encounter's outcome residual is 1 − 0.80 = 0.20. Its risk/procedure-normalized cost is $150 / 1 / 1.5 = $100.

The existing SQL pipeline averages residuals only over recorded outcomes and averages normalized costs over encounters. It calculates raw average cost separately. The provider's normalized cost is compared with its specialty benchmark. Missing outcomes contribute to encounter counts and costs but not observed outcome counts or residual averages.

The existing Python scorer shrinks effects toward neutral using n/(n+50), where n is observed outcomes. It calculates outcome, cost, reliability and volume components. Only providers with n ≥ 30 and completeness ≥ 80% get a final score and specialty rank.

That single encounter is not a provider rating. It contributes to aggregates with many other events. The API never sends this encounter to the browser. The graph receives only the resulting provider ID, name, raw average cost, stored quality and a descriptive highlight flag. This example illustrates arithmetic; it is not evidence of real medical quality.

## 4. API contract: quality and cost

File: `backend/app/main.py`; implementation: `backend/app/analytics.py`; schemas: `backend/app/schemas.py`.

GET `/api/analytics/quality-cost?specialty=Cardiology`

The specialty parameter defaults to Cardiology, must have 1–50 characters, and is bound through SQLAlchemy. Unknown specialties return HTTP 200 with an empty cohort, not a silent all-specialty fallback. Invalid length returns 422. Existing database exception handling returns a sanitized 503 on SQL failures.

| Field | Meaning |
|---|---|
| specialty | Requested comparable specialty |
| count | Number of eligible provider points; equals items length |
| mean_cost | SQL AVG of eligible providers' raw avg_cost, or null if empty |
| mean_score | SQL AVG of eligible providers' quality, or null if empty |
| items[].id / name | Existing profile identity |
| items[].avg_cost | Raw mean encounter cost stored by the original pipeline |
| items[].quality | Stored non-null heuristic score |
| items[].highlighted | avg_cost < mean_cost AND quality > mean_score |

Pydantic models CohortPoint and QualityCost specify the response and OpenAPI contract. No encounter fields, patient IDs, score recalculation or mutations are introduced.

The implementation executes two queries in the existing repeatable-read session. First it calculates means from the eligible specialty cohort; then it selects all points in stable provider-ID order. Repeatable-read keeps those queries on the same snapshot if a pipeline refresh commits during the request. Separate requests may see different completed snapshots; no cross-request snapshot identifier was added.

Representative SQL (actual queries are constructed with SQLAlchemy):

```sql
SELECT avg(s.avg_cost), avg(s.quality)
FROM providers p JOIN scores s ON p.id = s.provider_id
WHERE p.specialty = :specialty AND s.quality IS NOT NULL;

SELECT p.id, p.name, s.avg_cost, s.quality
FROM providers p JOIN scores s ON p.id = s.provider_id
WHERE p.specialty = :specialty AND s.quality IS NOT NULL
ORDER BY p.id;
```

There is intentionally no LIMIT or OFFSET. The small simulated dataset makes full-cohort delivery reasonable. This is not an unbounded encounter export. No new performance benchmark or query-plan measurement is claimed.

## 5. API contract: evidence

GET `/api/analytics/evidence`

The Evidence response has total, specialties and completeness. Each specialty object has specialty, eligible, insufficient_outcomes, low_completeness and not_processed. Completeness contains named buckets with provider counts. An empty database returns total zero, no specialty rows and zero-count completeness bins.

Both queries start from providers and LEFT JOIN scores. An inner join would silently drop providers missing materialized scores, so it would conceal a useful data-processing failure.

The first query groups by specialty and an ordered CASE expression:

| Priority | Condition | Category |
|---|---|---|
| 1 | Score row missing | not_processed |
| 2 | Stored quality non-null | eligible |
| 3 | Observed outcomes < 30 | insufficient_outcomes |
| 4 | observed × 5 < encounters × 4 | low_completeness |
| 5 | Otherwise unscored unexpectedly | not_processed |

The stored quality remains authoritative. The fallback catches unexpected unscored records that pass the stated evidence thresholds. The UI calls this category “Not processed / unavailable” and explains it. Integer cross-multiplication tests 80% without relying on rounded JSON completeness. A provider with 20 encounters and 10 observed outcomes fails both rules but contributes only to insufficient_outcomes.

The query shape is SELECT specialty, CASE ... END, COUNT(*) GROUP BY specialty, CASE ... END. Python pivots these small grouped counts into response rows and sums them for total. It does not load encounter rows or reimplement the score.

The second query assigns one completeness bucket and counts it. Missing score rows and zero encounters are handled first. Otherwise it uses CAST(observed AS FLOAT) / NULLIF(encounters, 0). NULLIF prevents division by zero. Boundaries are 0–<20%, 20–<40%, 40–<60%, 60–<80%, and 80–100% inclusive of 100. Providers at 800/1001 completeness remain below 80%, even if a display rounds them close to 80%.

The histogram also includes No encounters and Not processed. Zero-count bins are supplied explicitly so the chart's shape and labels are stable across refreshes. The sum of all bins equals total; the sum of all specialty categories also equals total. These are two views of the same providers, not totals to add together.

## 6. React components and interactions

All new chart components live in `frontend/src/Analytics.tsx`.

| Component | Responsibility |
|---|---|
| AnalyticsPage | Owns specialty state, requests metadata/cohort/evidence, renders independent loading/error states, and forwards profile navigation |
| Scatter | Scales provider values into an SVG viewBox, draws axes/means/points, owns focused/hovered point information and renders the complete alternative table |
| EvidenceCharts | Renders mutually exclusive eligibility stacks, legends, exact count table and completeness bars; handles the empty dataset |
| ComparisonChart | Draws grouped component bars, provider legend, numeric contributions table and interpretation text; receives existing comparison data |
| Pending | Announces loading or an error for each independent analytics request |

Cohort and Evidence TypeScript types describe the new API responses. Existing Provider data is reused for comparisons. Shared constants define component keys/labels/weights, category labels/colors, and provider colors. These weights mirror the unchanged score for presentation only; the browser does not calculate authoritative ranks.

The existing App state union gains analytics. The new sidebar button has the correct aria-current state, and the existing Provider Explorer button no longer appears active merely because the page is not Overview. The Overview receives an analyze callback. Details renders ComparisonChart only when two or more IDs are being compared, then renders the original profile cards.

The chart has a 720×400 internal coordinate system and responsive width. Its y scale stays 0–100. Its x scale starts at zero and ends above the maximum cohort cost. The SVG gives stable axes without a resizing library. Eligible points expose a button role, accessible name, tab stop, click handler and Enter/Space handler. Diamond shape supplements color for the highlighted subset. The alternate table remains the most precise view on a narrow screen or in a dense cluster.

Evidence and component bars use percentage widths within labeled HTML tracks. The evidence stack represents each specialty's proportions and displays counts; comparison widths use the same absolute 0–100 component scale. CSS collapses comparison groups into one column on narrow screens, lets legends wrap and scrolls wide tables inside their own container.

## 7. Why no added chart library?

A library such as Recharts can be appropriate for complex chart interactions. This upgrade needs one bounded scatter and simple grouped/stacked bars. Native SVG plus semantic HTML lets the implementation explicitly own keyboard profile actions, data-table alternatives and empty states without changing dependency versions or the lockfile.

The tradeoff is responsibility for scales, ticks, hit targets and accessibility. Those behaviors are implemented and unit-tested, but visual mobile/browser approval still requires the local Playwright run. Overlapping points are expected; no jitter was added because jitter would change apparent data positions. The complete table handles occluded points.

No decorative time series or trend charts were added because the dataset has no encounter dates or longitudinal evidence supporting them. No clinical uncertainty bounds were invented.

## 8. Request reliability and edge cases

The existing useApi hook aborts old requests when the URL changes or the component unmounts. Crucially, it also checks controller.signal.aborted after the JSON body resolves. Abort alone cannot prevent an already-resolving old body from overwriting newer state. The prior delayed-response regression test remains unchanged and passes.

The new specialty selector uses this same hook. Different panels make independent requests, so evidence errors do not erase an available cohort and vice versa. Loading is announced with role=status; errors use role=alert. The metadata list retains the currently selected specialty if metadata is unavailable. To retry a failed panel, navigate away and back after addressing the connection problem.

No eligible providers yields a clear empty-cohort message. Null means are not converted into fake plotted values. Providers with absent or null scores are excluded from the scatter but remain visible in evidence counts. An empty evidence database shows an instructional message, not a meaningless zero-width chart. Same-specialty and distinct-ID comparison rules remain enforced by the original backend.

## 9. Tests and what they establish

New portable tests in `backend/tests/test_analytics.py` create an isolated in-memory SQLite database, populate provider/score rows and call FastAPI through TestClient. They execute real SQL expressions and serialization, not mocked query results. They cover more than 100 eligible points, aggregate means, strict highlighting, all exclusion boundaries, both-rule precedence, absent scores, empty databases and invalid specialties.

SQLite validates the portable query logic but not PostgreSQL execution, driver behavior, repeatable-read isolation or query plans. `test_postgres_cohort_and_evidence` in the existing integration suite adds a PostgreSQL-specific execution path and conservation assertions. It requires TEST_DATABASE_URL pointing to a disposable database; the integration fixture drops and recreates schema.

`frontend/src/Analytics.test.tsx` covers point hover/focus/click/Enter, table navigation, full-cohort rendering, specialty requests, loading/errors/empty states, evidence category explanations, weighted table values, unscored labeling and new App navigation. Existing tests retain the race regression. These are DOM tests, not actual browser screenshots.

`frontend/e2e/workflow.spec.ts` now has a second real-browser flow. It validates complete cohort point counts, changes specialties, captures Analytics and mobile Analytics, checks horizontal overflow and opens a profile using the keyboard. The original flow continues to cover Overview, search/pagination, two-provider comparison, profile and mobile Overview. The GitHub Actions artifact list includes the new screenshots.

Executed on this delivery: 28 backend tests passed and 14 PostgreSQL tests skipped; 13 frontend tests passed and 1 optional live test skipped. The production build, Ruff, Prettier and three launcher regression tests passed. Compose parsed successfully. Docker engine access was unavailable. Playwright's first browser launch aborted before navigation; one test failed and one did not run. No screenshot or live 2.0 browser success is claimed.

## 10. Upgrade and verify without losing your data

Use `UPGRADE_2.0_MAC.md` for the exact beginner steps. Extract the new ZIP separately, remain in your original project directory, back up the database, and copy source with exclusions for .env, .git and local runtime folders. The source-copy command does not use --delete. Preserve any personal source edits before replacing files.

Build api and web. Start api using --no-deps, check its health, then recreate web using --no-deps so Nginx resolves the replacement API container. This avoids running the seed dependency. Do not use a fresh-install script for the upgrade. No volume removal or schema migration is needed.

Verify the original provider/encounter counts and .env checksum before and after. Check both new endpoints through localhost:8080. Run the browser test and inspect its seven screenshots. PostgreSQL integration tests must use a separate test database, never your current carerank database.

For a small first code change, edit the Analytics heading in Analytics.tsx. Run npm test and npm run build in frontend. For Docker, rebuild/recreate only web. For native frontend development, run npm run dev while the API remains available on port 8000; Vite proxies API requests. Restore the original text when finished. This exercise connects source, build and visible behavior without touching data.

## 11. Files to read in order

| File | Question it answers |
|---|---|
| README.md | What problem is solved, and how do I run it? |
| docs/UPGRADE_2.0_MAC.md | How do I preserve my environment while upgrading? |
| frontend/src/Analytics.tsx | What does each graph show and how does interaction work? |
| frontend/src/App.tsx | How do navigation and existing profiles connect? |
| frontend/src/api.ts + api.test.tsx | How are stale responses prevented? |
| backend/app/main.py + schemas.py | What is the API contract? |
| backend/app/analytics.py | Which SQL aggregates feed the graphs? |
| backend/app/aggregate.sql + scoring.py | Where do stored components actually come from? |
| backend/tests/test_analytics.py | Which missing-data and boundary cases are tested? |
| frontend/src/Analytics.test.tsx | Which chart interactions are verified? |
| frontend/e2e/workflow.spec.ts | How are actual browser flows and screenshots captured? |

## 12. Portfolio readiness and honest ownership

Source, tests, documentation and the existing Docker configuration are packaged together. .env, virtual environments, node_modules, caches, build output, browser traces and local database files are excluded. There are no real patient records. No GitHub publishing, remote CI run or public deployment was performed.

Before showing this project, complete the local database/browser checks, inspect screenshots, and open this Word document to check pagination. This document was structurally validated, but rendered Word pages were not available in the delivery environment. Earlier reports and benchmarks in the repository describe earlier work, not a 2.0 verification pass.

AI assisted the implementation, test authoring and documentation. Prabhat defined the goals; no independent human review or code authorship beyond that is asserted. A strong demonstration is being able to explain one graph end-to-end, identify what remains unverified and describe how a failing test would guide a fix. The two-minute demo script provides a concise route through that explanation.

# CareRank Lab Interview Preparation

Prepared for Prabhat Mattaparthi. Use this guide to practice explaining and changing the implemented software. The scripts below are examples you may adapt after you reproduce the workflow. They distinguish AI-assisted implementation from your own learning and avoid unsupported clinical or performance claims.

## Thirty second elevator pitch

“CareRank Lab is an AI-assisted educational provider analytics platform. It generates 100,000 synthetic encounters, validates and loads them into PostgreSQL, calculates transparent specialty-level scores, and exposes them through FastAPI and a React dashboard. I focused on understanding data quality, transactional reruns, API design and score explainability. It is independent of Garner and uses no real patient data or proprietary clinical methodology.”

## Two minute walkthrough

“Start with the user: someone wants to search a provider cohort and understand why a provider received a score. The Overview page shows coverage, score distribution and last successful refresh. Explorer filters by specialty, location, score and cost. A profile exposes counts, completeness, shrinkage and component scores. Comparison only accepts providers in the same specialty.

“Underneath, a seeded Python generator creates providers and encounters. Pydantic validates rows, and the pipeline checks duplicates and foreign references before writing. PostgreSQL normalizes costs and averages outcome residuals. Python applies shrinkage and an explicit weighted heuristic. Low evidence means no score, not a score of zero.

“The pipeline replaces the dataset atomically, and a separate execution audit records failures. FastAPI reads materialized scores through SQLAlchemy. The tests include scoring boundaries, failed-run rollback and a live React-to-PostgreSQL workflow. ChatGPT generated the implementation and tests; my next step is to reproduce the checks and complete the code modifications so I can explain and maintain it myself.”

Change the final sentence only after you have personally done that work. Do not present a learning goal as a completed contribution.

## Five minute technical walkthrough

Minute 1: explain the product boundary. All records are fictional. There are five specialties, and comparisons are limited to one specialty. Open the Overview page and explain that a score distribution is descriptive, not a clinical performance claim. Point to freshness and the disclaimer.

Minute 2: trace one request. Changing a filter updates URLSearchParams and useApi. Fetch goes through Vite during development or Nginx in Compose. FastAPI validates the request, repository.search applies bound SQL filters, PostgreSQL returns a count and page, and Pydantic serializes the response. React renders loading/error/empty states. Request sessions use one repeatable-read snapshot.

Minute 3: trace the pipeline. Generate deterministic lists, validate schemas/IDs, create a durable audit, lock the writer transaction, replace rows in batches, run SQL normalization and aggregation, score, rank within specialties, then commit. Explain that a scoring exception rolls the dataset back while a separate transaction records failure. A process kill may leave a stale running audit: that is a known gap.

Minute 4: work through scoring. The expected outcome is 0.95 minus 0.30 times synthetic risk. Average observed-minus-expected residuals and shrink with n/(n+50). Normalize cost for procedure and risk, compare against specialty cost, and combine 60% outcome, 25% cost, 10% reliability and 5% volume. Require 30 observed outcomes and 80% completeness. A score is not a probability or proof of treatment benefit.

Minute 5: discuss evidence and tradeoffs. Backend and live DOM tests were executed. The benchmark measures one 100,000-event pipeline and warm in-process search calls, not production throughput. Browser execution and Docker startup remain to be verified outside the restricted build environment. Explain the choice of a small modular monolith, and name the first production changes: authentication, separate database roles, immutable dataset versions and clinical validation.

## Architecture in your own words

The browser owns interaction state. The API owns request validation and HTTP responses. The repository owns database queries. PostgreSQL owns persistence, constraints and set-based aggregation. Pure Python scoring owns the heuristic. The pipeline owns the write workflow. The audit table owns a record of attempts. Avoid saying that one tool “does everything”; knowing the boundaries is the point.

## Why these technologies

Python fits generation, analysis and a backend you can already read. FastAPI makes typed endpoints and OpenAPI straightforward. Pydantic validates external data rather than trusting dictionaries. SQLAlchemy keeps parameters bound and isolates query construction. PostgreSQL supplies joins, transactions and aggregations. React and TypeScript make UI behavior explicit and type-checkable. Vite handles local development and static builds. Docker Compose describes local services; GitHub Actions describes repeatable checks. Pytest, Vitest and Playwright address different layers of correctness.

## Ranking and pipeline explanation

Use the worked example in the technical guide: 100 total and observed outcomes, residual 0.04 and cost ratio 0.80 produce a 57.33 score. Show what happens at 29 observed outcomes or 79% completeness. Explain the difference between raw mean cost in the search filter and the normalized cost used in the score. Describe why zero events must remain visible through a LEFT JOIN and why COUNT(outcome) differs from COUNT(event ID).

## Performance scalability and privacy

Read docs/benchmark.json for the measured numbers. State the dataset, warmup count, query shape, process boundary and hardware/environment limitations before quoting a number. The current design keeps batches in memory and rebuilds all scores. For millions of events, measure COPY ingestion, incremental aggregates, indexes and partitioning. Adding Kubernetes first would not fix an inefficient SQL query.

No real patient data is used. Local credentials are generated and ignored by Git. Queries bind input parameters, React escapes text and endpoints are read-only. The local demo has no authentication and shares a DB role between API and pipeline; it is not ready for public exposure or PHI. Explain these limitations directly rather than claiming compliance.

## Twenty five technical interview questions

### 1 What problem does the project solve?

It demonstrates how to turn synthetic encounter records into inspectable provider evidence and a searchable product. The implemented value is the engineering workflow; actual healthcare benefit has not been established.

### 2 How is the code organized?

The backend separates generation, input validation, pure scoring, orchestration, database models, query functions and HTTP routes. React separates request state from typed views, though the small page components share App.tsx. Tests and migrations are separate from runtime entry points.

### 3 Why FastAPI rather than Flask?

FastAPI integrates typed query validation, response schemas and OpenAPI with little glue. Flask could implement the same product, but would need more explicit choices for those concerns. Framework selection is not itself a performance result.

### 4 What does SQLAlchemy do that psycopg does not?

Psycopg connects to PostgreSQL and executes protocol operations. SQLAlchemy adds models, query expressions, session management and pooling above the driver. The aggregation still uses explicit static SQL because it is clearer as a set-based transformation.

### 5 Why PostgreSQL instead of a CSV or SQLite?

The exercise needs relational constraints, transactional replacement, SQL aggregation and concurrent read behavior. PostgreSQL makes those features part of the actual system. CSVs lack transactions, and SQLite would not verify the PostgreSQL-specific writer lock.

### 6 How is synthetic generation reproducible?

A private random.Random instance and explicit seed control all draws. IDs and specialty assignment are deterministic. Reproducibility also depends on generator code and runtime version, so the seed alone is not a universal dataset identity.

### 7 How do you detect duplicates and bad records?

Strict Pydantic schemas reject invalid fields and numeric values. Sets detect repeated provider/encounter IDs, and an encounter reference must exist in the provider set. Validation rejects the whole batch before writes; no silent deduplication chooses an arbitrary winner.

### 8 What happens to missing outcomes?

They remain NULL. SQL excludes them from outcome averages and COUNT(outcome), while total encounters still includes them. Completeness decreases, and below 80% the overall score is withheld. Missingness could be biased in reality; the demo does not solve that.

### 9 How is risk adjustment implemented?

For each observed event, expected success is 0.95−0.30×risk. We average actual minus expected outcomes. This adjusts against a known simulation baseline and is not a trained or validated clinical model.

### 10 How do you protect against small samples?

At fewer than 30 observed outcomes there is no overall score. Above that, outcome and cost deviations are shrunk toward neutral with n/(n+50). This stabilizes the demonstration but supplies neither a confidence interval nor formal clinical reliability.

### 11 What are the score weights and why?

The heuristic weights are 60% outcome, 25% cost, 10% reliability and 5% volume. They make quality dominant while exposing cost and evidence. They are educational policy choices; changing them requires score versioning and sensitivity analysis, not a claim of medical truth.

### 12 Why compare only within specialty?

Procedure mix, expected care and cost structures differ across specialties. The cost benchmark and ranks are specialty-specific, and the API rejects mixed comparisons. The global mean is only a descriptive summary, not a valid cross-specialty league table.

### 13 How are tied scores ranked?

The engine uses competition ranks on stored two-decimal scores. Equal values share a rank, so 1,1,3 is possible. Provider ID gives deterministic iteration order without turning a tie into a performance distinction.

### 14 Why use LEFT JOIN in aggregation?

Providers with no encounters must remain represented and explicitly unscored. An inner join would hide them. COUNT(event ID) is zero on a missing event join; COUNT(*) would incorrectly count the preserved provider row.

### 15 How do reruns avoid duplicates?

The pipeline replaces the current provider, encounter and score snapshot in one transaction under an advisory writer lock. Primary keys also enforce uniqueness. Audit rows accumulate intentionally. This is idempotent in dataset content, not in execution history.

### 16 What happens if scoring fails halfway through?

The data transaction rolls back, preserving the previous dataset and scores. A separate transaction updates the existing audit to failed with an exception class. If the entire process or database disappears, the row may remain running; stale-run recovery is future work.

### 17 How do you prevent SQL injection?

User filter values are bound through SQLAlchemy, while sort choices use a fixed allowlist. Literal substring search escapes SQL wildcard characters. The aggregate SQL is static and contains no interpolated user input. Tests use injection-shaped strings and a literal percent sign.

### 18 How does pagination work?

Filters are applied before the total count and before limit/offset. Quality sorts descending with NULL last, then ID breaks ordering ties. A repeatable-read request transaction keeps count and page consistent during refresh. Large offsets would motivate cursor pagination.

### 19 Why materialize scores?

It avoids reaggregating 100,000 events for every search. The tradeoff is refresh latency and more write work. The UI exposes successful refresh time so the user can inspect freshness. Versioned snapshots would improve historical auditability.

### 20 How does the frontend handle races and errors?

useApi creates an AbortController for each URL and aborts on cleanup when filters change. It resets loading state and renders safe error text on failed responses. The UI shows empty results separately from network failure and null scores separately from zero.

### 21 What did your tests actually verify?

The report records backend unit/integration tests against PostgreSQL, React component tests, a real HTTP-backed DOM workflow, lint and a production build. The Playwright browser test was authored and attempted but could not launch in the restricted environment; Docker also was unavailable.

### 22 What did the benchmark measure?

One default generation/validation/load/aggregate/score run and 100 warmed repository search calls with five warmups. Each search includes count, page retrieval and serialization for Cardiology. It excludes HTTP transport, browser rendering and concurrency, so it is not a service latency SLA.

### 23 What would you change for production?

First establish data authorization and clinical governance. Then add authentication/authorization, least-privilege DB roles, TLS, managed secrets, backups, monitoring, rate limits and versioned datasets. Profile real workloads before choosing streaming or distributed infrastructure.

### 24 Why did you omit dbt, Airflow and Kubernetes?

One short aggregation and one local CLI do not justify their operating overhead. dbt becomes valuable with many dependent SQL models; Airflow with scheduled dependencies and retries; Kubernetes with an actual multi-service deployment need. Their absence is a scoped decision.

### 25 How can you demonstrate ownership if AI wrote the code?

I should be precise about the generated baseline, reproduce the tests, explain the SQL and score by hand, implement a meaningful change, and show its diff and test evidence. I should not claim independent authorship or mastery before doing that work.

## Honest answers about AI assistance

“Did you write all of this yourself?” — “No. ChatGPT generated the initial implementation, tests and guides under my specification. I can distinguish that baseline from changes I have personally made.”

“How did you verify the AI output?” — “The agent executed the tests and build checks recorded in the report. I still need to reproduce them myself before claiming independent verification. The browser and Docker checks need an unrestricted local environment.”

“What did you personally contribute?” — “I chose the project scope and learning goals. I will identify my own completed code changes by commits and tests, rather than attributing generated code to myself.” Replace this only with factual, completed work.

“What would you do if the AI was wrong?” — “Reduce the issue to a failing test or reproducible request, inspect assumptions and SQL, apply the smallest correction, and rerun relevant checks. I would not treat generated documentation as independent evidence that the code is correct.”

“Can you code without AI?” — Demonstrate this through an exercise instead of giving an unsupported assurance. Explain the logic before typing and state what reference material you use.

## Five progressively harder coding exercises

1. Add an evidence label to the UI and test the 49/50 boundary.
2. Implement minimum observed outcomes filtering through API, SQL query and UI.
3. Introduce a validated immutable evidence policy without changing default scores.
4. Strengthen failure rollback tests to compare actual stored scores across an injected exception.
5. Add mean synthetic risk through a migration, aggregation, schema, UI and independent SQL test.

Detailed instructions are in docs/EXERCISES.md. Solutions are deliberately separate in docs/EXERCISE_SOLUTIONS.md. Work on one branch per exercise and keep a short learning log: what changed, why, how you tested it, and one limitation.

## Final practice session

Run the app, then give the two-minute walkthrough without reading. Draw the request and pipeline paths from memory. Calculate the 57.33 worked example. Change a filter and identify the exact database condition it adds. Trigger a deliberate invalid batch on a disposable database. Finally, explain one unresolved limitation calmly and concretely. These tasks establish genuine understanding better than memorizing the model answers.

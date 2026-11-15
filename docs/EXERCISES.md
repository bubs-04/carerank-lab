# Five Hands On Exercises

Work on a branch, write a failing test first where useful, and explain your change aloud before opening the solutions.

## 1 Evidence label

In `frontend/src/App.tsx`, show “Limited evidence” beside the encounter count for providers with fewer than 50 observed outcomes. Keep insufficient-data scores unchanged. Add a component test and verify 49 and 50 are different boundaries.

## 2 Minimum observed outcomes filter

Add an optional `min_observed` integer query parameter (0 or greater) through `main.py`, `repository.search` and the Explorer form. Update every call site, including the benchmark. Test omitted, zero, positive and negative values, plus pagination totals after filtering.

## 3 Configurable evidence policy

Extract the 30-outcome threshold and 50-pseudo-observation shrinkage strength into a validated immutable policy object in `scoring.py`. Pass it into `score_provider` without changing default outputs. Test a threshold of 40 and a strength of 100. Decide how a policy change should update the stored score version.

## 4 Transactional rollback under load

Add an integration test that succeeds once, then injects a scoring error during a second pipeline run. Verify provider IDs, encounter count and score values remain unchanged, and the latest audit is failed. Extend the existing rollback test to compare actual stored scores, not just counts. Explain why audit and dataset use different transactions.

## 5 Benchmark integrity and clinical humility

Add a provider-level mean synthetic risk to the stored score and detail response using a new Alembic migration, SQL aggregate, model field and UI row. Add a test that independently calculates the mean from encounter rows. Verify migration upgrade/downgrade on a disposable database and rerun the benchmark. Explain why a higher risk average does not itself prove a provider delivers better care.

Solutions are in EXERCISE_SOLUTIONS.md. Record your own implementation, test output, and what surprised you; those are the most valuable interview notes.

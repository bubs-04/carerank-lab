# Five hands-on engineering exercises

Work on a separate local branch and use fixtures/a disposable test database. Do not alter your real `.env` or production-like history for an experiment.

## 1. Predict a threshold boundary

Read `monitoring/rules.py` and find rejected_rate. Predict the result for observations 4.99, 5, 5.01 and None with threshold 5. Run `pytest -q tests/test_monitoring.py -k threshold_boundary`. Explain why None is not zero. Expected: passed, passed, failed, not_evaluable. Add a test for another fractional boundary and run it.

## 2. Version a threshold without erasing evidence

Read test_new_rule_threshold_preserves_prior_evidence. Run it, then change its second threshold from 30 to 19 and update the expected outcomes. Confirm the old observation and original rule version remain. Explain why editing the old database row would undermine reproducibility. Revert your exercise edits afterward.

## 3. Make two snapshots intentionally incomparable

Read baseline_for and test_incompatible_history_is_not_a_baseline. Add a test for a changed selected-field scope hash, then run `pytest -q tests/test_monitoring.py -k incompatible`. Explain why having 1,000 rows in each sample is insufficient if the selection policy differs. Check that no baseline-dependent rule is mislabeled passed.

## 4. Investigate, resolve, then reopen a fixture alert

Use the upgrade guide's inspect command. Add an investigating note with the current revision, then resolve it with a reason and the next revision. Inspect again and reopen it. Predict which field is cleared (current resolution) and which data remains (all historical events). Try reusing an old revision; verify it fails without a new event. Do not resolve a real incident just to finish this exercise.

## 5. Improve the dashboard with a tested change

Read Monitoring.tsx and its React tests. Add a short explanation next to the warning-finding count that one row can have several warnings. Write a test for the explanation using a semantic query. Run `npm test` and `npm run build`. Then run the monitoring Playwright workflow in a supported local browser. Explain why a passing React DOM test alone cannot prove mobile visual layout.

For an interview, describe what you predicted, which evidence you inspected, what failed initially, and what the final test demonstrated. Do not present an unexecuted check as a result.

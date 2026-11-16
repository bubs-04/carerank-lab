# Five hands-on exercises

Use fixture mode and a disposable database. Preserve your normal synthetic/live data. Commit each exercise separately, and run the relevant tests before keeping it.

## 1. Repair a rejected record

Copy `backend/tests/fixtures/cms_registry_a.csv` to a new fixture file. Replace the invalid NPI on row 4 with a distinct 10-digit value beginning with 1 or 2. Do not claim it is an assigned real NPI. Run the CLI for five rows. Expected: valid increases from 4 to 5, rejected drops from 1 to 0; three optional warnings remain. Inspect the finding and version differences. Explain why the NPI becomes part of a newly accepted source identity.

## 2. Separate warnings from errors

Fill in the missing specialty, city and state on row 5. Keep its four identity fields unchanged. Ingest as a new fixture. Expected: valid/rejected counts remain 4/1, warning findings drop by three, and the retained record changes. Add a test asserting `validation_delta['missing_optional'] == -3`. A corresponding baseline regression already shows the pattern; write your own distinct case rather than merely copying assertions.

## 3. Challenge identity with duplicate locations

Copy row 1 over row 3, keeping row 2's different address key. Both copies of row 1 must be rejected as duplicates; row 2 should remain accepted despite sharing the NPI. Add an assertion that no duplicate accepted key is stored. Explain why deduplicating by NPI would lose valid enrollment/location information.

## 4. Simulate a failed download and preserved history

In a new test, use httpx.MockTransport with a stream that raises ReadError after a chunk. First ingest a successful fixture. Run the failing connector and check: the attempt fails, there is no new snapshot, the prior version remains, and no partial provider rows publish. Then simulate HTTP 503 and check bounded attempts/backoff; compare with HTTP 403, which should not retry. Never perform this exercise by breaking your main database.

## 5. Add one useful presentation improvement

Add a small “Rows needing review” explanation to DataOps.tsx using the existing rejected count and warning-finding count, keeping their units separate. Do not sum them as though they were distinct rows. Add a Testing Library assertion for the wording. Run `npm test`, `npm run build`, and the opt-in browser workflow against fixture data. Explain which API fields supply the UI and why a frontend-only label change needs no migration.

After all five, explain in your own words: REST request vs CSV stream; record key vs content checksum; run vs snapshot; rejected row vs failed batch; and snapshot transaction vs separately committed attempt audit.

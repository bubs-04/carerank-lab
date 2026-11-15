# CareRank Lab Beginners Guide

Prepared for Prabhat Mattaparthi. Your first goal is to open the existing website, click through it, and understand one provider's score. You do not need to understand every file before you begin. Your Python and SQL experience will help once the visible pieces make sense.

You have since reported that the original website opens on your Mac and comparison works. You can begin with Lesson 3. To apply the small reviewed fix to that working copy, read docs/APPLY_UPDATE.md; you do not need to reinstall Docker. Your report is a manual check of the original version, not automated verification of this update.

This is a learning project using fictional data. A high score is not evidence that a real doctor gives better care. CareRank Lab is independent of Garner. It demonstrates software ideas relevant to provider analytics; it does not use Garner's data or reproduce its methods.

## Lesson 1 What you received

Think of the project ZIP as a box containing a small shop's plans, equipment instructions and sample inventory. The box is not an open shop yet. Running the application starts the pieces that make the website respond.

The product lets you look through fictional healthcare providers, filter them, examine their simulated outcomes and costs, and compare two or three providers in the same specialty. You are the person exploring the data. There is no patient login, appointment booking, insurance enrollment or real medical recommendation.

A provider is one fictional doctor-like entry. An encounter is one fictional visit or treatment event assigned to that provider. The default dataset contains 1,000 providers and 100,000 encounters. Providers are distributed across Cardiology, Dermatology, Orthopedics, Primary Care and Neurology. The generator uses five city labels. These labels are part of the demonstration, not a directory of real practices.

The source repository contains instructions for generating data, storing it, scoring it and displaying it. It does not ship a permanent database of 100,000 records inside the ZIP. Startup generates those records for you. The same seed, generator and runtime make the sample repeatable.

**Your first checkpoint:** Explain the difference between a provider, an encounter and a score in your own words. A score is a summary calculated from many encounters; it is not a column that was copied from real medical records.

## Lesson 2 Open it on your Mac

Use the separate MAC_SETUP_GUIDE.md for the full installation steps and error lookup table. Here is the short path once Docker Desktop is installed and running.

1. Double-click the delivered updated ZIP in Finder. Find the carerank-lab folder containing compose.yaml.
2. Open Terminal. Type cd followed by a space, drag that folder into Terminal, and press Return.
3. Run the following command. It checks Docker, creates a local private password if needed, and starts the existing application.

```bash
bash scripts/start_mac.sh
```

4. Check the five services. Exited (0) is normal for migrate and seed because they are one-time jobs.

```bash
docker compose ps -a
```

5. Check the website's connection to the API, then open the website.

```bash
curl -fsS http://localhost:8080/api/health
open http://localhost:8080
```

The health request should return {"status":"ok"}. The Overview page should show 1,000 providers and 100,000 encounters with the default dataset. Health alone does not prove those counts; look at the page and the database-count check in the Mac guide.

A container is an isolated running environment for a service. Docker Compose starts a set of related containers from compose.yaml. For the first launch you need Docker Desktop, not separate installations of every technology listed in the technical guide. Node is needed on your Mac only if you choose to run frontend development tools outside Docker.

localhost means this Mac. 8080 is the website's port, like a numbered door. 8000 is the API's door. 5173 belongs to the optional frontend development server. Open 8080 for the Docker version. Opening frontend/index.html directly in Finder does not launch the full application.

**If this stops here:** copy the exact error and consult the Mac guide. This agent's Docker socket, database shared memory and Chrome launch were restricted. Your own Terminal may work normally. No Docker or real-browser pass is claimed for this review.

## Lesson 3 Read the Overview page

The left navigation contains Overview and Provider explorer. The CareRank LAB brand also returns you to Overview. The workspace name and the PM initials identify this portfolio workspace; they are decorative and are not a login account. There is no authentication system behind them.

The top disclaimer says that the data and scores are synthetic. Keep that visible if you show the project in an interview. The page headline is “Provider intelligence, explained.” The Explore providers button opens the searchable list.

| Visible item | How to read it |
|---|---|
| Providers analyzed | Count of fictional providers in the current database. Default: 1,000. |
| Encounters processed | Count of fictional encounter records. Default: 100,000. |
| Eligible for ranking | Providers meeting both the 30-observed-outcome and 80%-completeness rules. Not everyone qualifies. |
| Mean demo score | Average of nonempty scores across this demo. It is descriptive, not a fair way to compare different specialties. |
| Specialty distribution | A bar for each specialty, showing provider count. The default has 200 in each specialty. |
| Quality score distribution | Counts in five score ranges. Providers without a score are excluded. Bars are summaries, not clickable filters. |
| Latest run | Status of the most recent pipeline attempt. It could fail even if an older dataset remains available. |
| Last successful refresh | When a complete dataset was last successfully stored. This differs from the latest attempted run. |
| Seconds per latest run | Recorded duration of that attempt; it will differ across machines. |
| Transparency explanation | The four component weights used by this demonstration. |

The charts and pipeline card have no run button. You rerun the pipeline from Terminal. Refresh the browser to see the new data; the app does not continually poll for updates.

**Try this:** Find the total encounter count, the latest attempt's status, and the time of the last successful refresh. Explain why these are three different facts.

## Lesson 4 Search and compare providers

Choose Provider explorer in the navigation or Explore providers on Overview. The table shows up to 12 providers per page. Clicking a provider name opens the profile; selecting its checkbox adds it to a comparison.

| Control | What it changes |
|---|---|
| Provider name | Searches for a literal substring in the fictional name. Type Demo Provider 0001 to find that entry. It is not a diagnosis search. |
| Specialty | Limits the list to one specialty. Start with Cardiology before interpreting rank or score order. |
| Location | Limits results to one city label. It does not calculate distance from your location. |
| Minimum score | Keeps providers at or above a number from 0 to 100. Empty means any score. Applying a numeric cutoff excludes unscored providers. |
| Maximum cost ($) | Keeps providers whose average raw encounter cost is at most this amount. Use a positive number. It is not the normalized cost component used in scoring. |
| Sort by | Quality score sorts highest first, with unscored last. Lowest cost sorts average encounter cost lowest first. |
| Checkbox | Selects or deselects a provider for comparison. You may select two or three in the same specialty. |
| Compare (number) | Opens the selected provider cards side by side. Disabled until at least two are selected. |
| Clear | Clears selected providers only. It does not reset search filters. |
| Provider name button | Opens that provider's individual profile. |
| Previous and Next | Move through result pages. Disabled at the beginning or end. |

Filters apply together. Setting Cardiology, Boston, minimum 60 and maximum 100 may produce no matches; that is not necessarily an error. Clear the numeric fields, choose All locations, then widen the search. Each filter change returns you to page 1.

Selection survives filtering and pagination while you remain in Explorer, so selected names may not be visible in the current table. Read the Selected line. If you change specialties and then select a different specialty, the app asks you to choose providers in the same specialty; choose Clear to begin a new comparison. Trying to select a fourth provider produces a limit message.

A specialty rank is calculated across the whole specialty, not just the filtered city or page. A provider can be first in your filtered list while having specialty rank 12. Tied stored scores share a rank. A badge saying Insufficient data does not mean zero quality or a bad doctor; the demo is withholding a score.

**Try this:** Choose Cardiology, select the first two checkboxes, and press Compare (2). Look at encounter counts and completeness before looking at which score is larger.

## Lesson 5 Understand a profile and the comparison page

An individual profile and each comparison card use the same layout. The avatar number is the fictional provider ID. The profile shows the name, specialty, city, overall score, specialty rank and score status. Comparison shows two or three such cards. On small screens the cards stack vertically instead of remaining side by side.

| Metric | Everyday explanation |
|---|---|
| Encounters | All events assigned to this provider, including those with missing outcomes. |
| Observed outcomes | Events for which a success/failure value exists. A missing value is not treated as failure. |
| Mean encounter cost | Average of the simulated dollar costs. The UI rounds dollars for display. |
| Outcome completeness | Observed outcomes divided by all encounters. 90 observed out of 100 is 90%. |
| Shrinkage weight | How much the demo trusts the observed deviation from neutral. More observed outcomes increases this weight. |
| Outcome residual | Average actual outcome minus expected outcome. “pp” means percentage points, not percent growth. |
| Normalized cost ratio | Procedure/risk-adjusted cost compared with the same specialty's baseline. Below 1 is lower than that baseline. |
| Score breakdown | Four component values from 0 to 100 and their weights: outcome 60%, cost 25%, reliability 10%, volume 5%. |

The progress bars are read-only displays. They are not sliders, and 60% beside outcome is the component's weight, not a patient's success probability. The “How to read these scores” section explains the rules.

Back to providers returns to Explorer. Because the current app remounts that page, filters and selections reset. The browser Back button is not the application's navigation system: the app uses React state, not separate URLs for every profile. Refreshing the browser returns to Overview. Those are known small-project tradeoffs.

The loading message means a request is in progress. An error panel means data could not be retrieved; Try again reloads the application and returns to Overview. The no-match message means the query completed successfully but found no providers for those filters. Those three states require different responses.

**Try this:** Choose one provider and explain its raw mean cost and normalized cost ratio separately. They measure different things.

## Lesson 6 The four moving parts

[Figure: system-map.png]

The frontend is the page you see and interact with. React creates it, TypeScript checks the shapes of data during a build, and CSS controls spacing, colors and layout. A filter change causes a request; the frontend does not directly log into PostgreSQL.

The backend is the Python API. FastAPI receives requests such as “give me page 1 of Cardiology providers.” It checks parameter values, asks the database for matching records and returns JSON. JSON is structured text containing names and values; React turns that text into visible cards and rows.

The database is PostgreSQL. It stores providers, encounters, scores and pipeline run history. SQLAlchemy helps Python express bound queries and map records. SQL joins connect related rows using IDs. Storing information separately from the website lets many requests reuse the same results.

The pipeline is a Python program you run when you want to refresh the demo. It creates fictional inputs, validates them, loads them, executes SQL aggregation, calculates scores and stores the results. The API usually reads the stored scores rather than recomputing all 100,000 encounters for each search.

In Docker, Nginx serves the built frontend and forwards /api requests to FastAPI. That forwarding is called a proxy. During optional native frontend development, Vite does the equivalent forwarding. This is why the browser can use one website address while another service answers data questions.

**Trace one click:** Specialty changes → Explorer builds a URL → useApi fetches JSON → Nginx or Vite forwards the request → FastAPI validates it → repository.search queries PostgreSQL → JSON comes back → React renders the new table. The changed URL contains query parameters, not SQL text supplied by the user.

**Checkpoint:** Without reading this page, name which part owns appearance, request validation, persistent records and dataset refresh.

## Lesson 7 Follow one encounter into a score

[Figure: encounter-map.png]

Imagine one generated event for Demo Provider 0001. This is a teaching example, not a promise that this exact row exists in your seeded dataset: procedure Diagnostic, synthetic risk 0.40, cost $600, outcome 1 (success).

First validation checks that the provider exists, the encounter ID is unique, cost is positive, risk is between 0 and 1, and the procedure is allowed. Duplicate IDs or invalid required values reject the batch. A missing outcome is allowed and counted as missing evidence.

SQL computes expected success as 0.95 − 0.30 × 0.40 = 0.83. The event's residual is actual outcome minus expectation: 1 − 0.83 = 0.17. If the outcome had been 0, its residual would be −0.83. If it were missing, it would contribute to the total encounter count but not the mean outcome residual.

SQL also normalizes cost. Diagnostic has a multiplier of 1.7. Divide $600 by 1.7 × (1 + 0.40), giving about $252.10. This removes the generator's procedure and risk multipliers. It does not establish what a real treatment should cost. The adjusted amount is compared with the same specialty's adjusted average.

One event is not enough for a provider score. SQL groups all that provider's encounters, counts total and observed events, and averages their residuals and relative costs. All providers are kept, including those with zero events.

For an easy worked provider example, suppose all 100 encounters have observed outcomes, their average residual is 0.04, and their average normalized cost ratio is 0.80. These summary values are separate teaching assumptions, not calculated from the one event above.

| Calculation | Result |
|---|---|
| Weight = 100 / (100 + 50) | 0.6667 |
| Outcome = 50 + 250 × 0.04 × weight | 56.6667 |
| Cost = 50 + 50 × (1 − 0.80) × weight | 56.6667 |
| Reliability = 100 × (100 / 100) × weight | 66.6667 |
| Volume = 100 × min(100 / 200, 1) | 50 |
| Overall = 0.60 × outcome + 0.25 × cost + 0.10 × reliability + 0.05 × volume | 57.33 stored |

Each component is bounded to 0–100. The overall score uses the unrounded component calculations; displayed components are rounded. The overall score is stored to two decimals and the badge displays one decimal, so you would see 57.3. Specialty ranking uses the stored score, not the rounded badge.

If only 29 outcomes were observed, there would be no overall score or rank. If 79 of 100 were observed, 79% completeness also means no overall score. The shrinkage weight pulls deviations toward neutral when evidence is scarce. It is a simple heuristic, not a clinical risk model or confidence interval.

The pipeline stores all changes in one database transaction: they succeed together or are rolled back together. A separate audit entry records ordinary failures. Refreshing the data replaces the demo snapshot instead of accumulating duplicate encounters. A process crash can leave a run marked running; recovery from that is not yet automated.

## Lesson 8 Read the code in a useful order

Do not open every folder at once. Begin with the visible feature you just used. You do not need to read generated lockfiles line by line.

| First files | What to look for |
|---|---|
| README.md and docs/MAC_SETUP_GUIDE.md | Startup commands, ports and known limitations. |
| frontend/src/App.tsx | Search for the visible heading. Find Overview, Explorer and Details. Follow a button's onClick or input's onChange. |
| frontend/src/styles.css | Find .primary for green buttons or .metrics for the metric-card grid. |
| frontend/src/api.ts | Find fetch, loading, error and cancellation. This is how components request data. |
| backend/app/main.py | Find @app.get("/api/providers"). Read the allowed query parameters. |
| backend/app/repository.py | Follow search: filter, count, sort, offset, limit, serialize. Your SQL knowledge helps here. |
| backend/app/generator.py and validation.py | Find the random seed, imaginary inputs and validation rules. |
| backend/app/aggregate.sql and scoring.py | Follow residuals, cost normalization, eligibility and weighted scoring. |
| backend/app/pipeline.py | Read the whole sequence and the try/except failure handling. |
| backend/app/models.py and migrations/ | See table fields and how the schema is created or changed. |
| backend/tests/ and frontend/src/*.test.tsx | Read assertions to learn what the software promises. |
| compose.yaml and .github/workflows/ci.yml | Read these after the services and tests make sense. |

A function is a named piece of work with inputs and outputs. A React component is a function that describes part of the page. An API route maps a URL to a backend function. A migration is a versioned database change. A test checks a specific expected behavior; it does not establish that everything else works.

## Lesson 9 Make your first small change

Start with a sentence, not a scoring rule. In a code editor open frontend/src/App.tsx. Find the Overview paragraph beginning “A clearer view of quality”. Change that paragraph to “My first CareRank Lab change.” Save the file.

For Docker, run these from the project root:

```bash
docker compose build web
docker compose up -d --no-deps web
open http://localhost:8080
```

Rebuilding creates a new frontend bundle. The second command replaces only the web service, so it does not deliberately rerun the data pipeline. Reload the page and look below the original headline. Leave the headline unchanged for this exercise because the automated workflow uses it to locate the page.

For faster editing later, install a supported Node version, run npm ci then npm run dev inside frontend, and open http://localhost:5173 while Docker's API stays running on 8000. Vite refreshes the page when you save. That is different from the built Docker page at 8080.

Run npm test and npm run build from frontend after your edit. Read the actual counts: a skipped live test is not a pass. Restore the original sentence and verify that it returns. Once Git is initialized, git diff shows exactly what changed. Do not use broad reset commands just to undo one sentence.

Now explain what happened: you edited a React paragraph; Vite built JavaScript; Nginx served the new bundle; the database and ranking logic did not need to change.

## Lesson 10 Troubleshoot by following the path

Start with the first broken link. If the website will not open, check docker compose ps -a. If the page loads but data does not, check http://localhost:8080/api/health, then API logs. If the API responds but counts are zero, inspect seed logs and the pipeline audit. If only one filter produces no rows, relax the filter before restarting services.

The Mac setup guide contains exact commands for each likely setup error. Always run them from the directory containing compose.yaml. Use only the relevant service's logs; do not share credentials. Never delete the database volume as your first troubleshooting step.

A real bug fixed during this review illustrates why tests matter. When a user changed filters quickly, an older response whose JSON body finished late could overwrite the newest results. AbortController requested cancellation, but the code also needed to check the cancellation signal before updating React state. A test in frontend/src/api.test.tsx made the old body finish last. It failed before the fix and passed after it. The fix is in frontend/src/api.ts. This is a precise example you can investigate, rather than simply claiming “AI tested everything.”

CI was also adjusted to wait for /api/health through the website's port 8080, rather than checking only API port 8000. A live API does not by itself prove the frontend proxy is ready. CI now retains browser screenshots and traces when available. Those workflow changes have not run on GitHub yet.

## Lesson 11 Know what has actually been checked

This review ran on a restricted Mac session. It generated and validated 1,000 providers and 100,000 encounters in memory, including 2,533 missing outcomes. It did not load that generated batch into a running Mac database. It passed 20 backend unit tests, a TypeScript/Vite production build, formatting checks, Compose syntax validation and 3 launcher tests using a fake Docker command. After your original app became reachable, all 6 frontend tests passed, including a simulated-DOM workflow that used real HTTP against your running service. Eleven additional read-only HTTP checks passed, confirming the default counts, filters, pagination, profiles, comparison and validation errors. The fake launcher tests do not establish that containers start.

Thirteen PostgreSQL integration tests were skipped because a test database could not run here. The live frontend test was initially skipped, then passed once your running app became reachable. This tests the revised React source against the unchanged running backend, but does not deploy the revised frontend into your Docker container. Chrome launch was attempted and aborted; the included Playwright test was discovered but its website workflow was not executed in this review. No Overview, Explorer, Profile, Comparison or mobile screenshots were captured. The diagrams in this guide explain code relationships; they are not screenshots.

The original delivered report records a different Linux run with 33 backend tests and 5 frontend/live tests passing, plus measured pipeline and search timings. Those historical records remain in the repository. They must not be described as a new Mac or Docker pass. See docs/MAC_VERIFICATION_REPORT.md for the current checks and remaining work.

When your own Terminal successfully runs the site and browser test, keep the output and screenshots. Add those verified facts to the report. Do not replace a blocked status with passed merely because configuration files look reasonable.

## Lesson 12 Prepare to explain and publish it

Git is local version history. GitHub is an online place to host it. Neither is needed to view the website locally. Complete the first tour and small change before worrying about publication.

The supplied ZIP excludes .env, installed packages, generated database files, caches and .git history. Read GITHUB_PORTFOLIO_GUIDE.md for initialization, your author identity, commits, branches and publication. Nothing has been pushed to your account. Before publishing, review staged changes, verify the actual browser, inspect screenshots, and confirm that no credentials appear in files or logs.

A useful learning sequence is: open and tour the website; trace a search request; calculate 57.33 by hand; change and test one sentence; complete Exercise 1; then attempt the harder exercises. Use docs/EXERCISES.md before opening the separate solutions.

When asked about AI, say: “ChatGPT generated the baseline and helped review it. I supplied the scope. I can show which checks ran and which changes I personally made.” Add claims of hands-on debugging only after you have done that work. Your strongest evidence is being able to change behavior, explain the diff, test it and describe a remaining limitation.

**Your next single step:** Open Docker Desktop, then run docker version in your own Terminal. If it shows both Client and Server, follow Lesson 2 to launch the site.

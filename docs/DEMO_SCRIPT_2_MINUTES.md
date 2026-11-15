# Two-minute CareRank Lab 2.0 demo

Before presenting: complete the Mac upgrade, run tests, inspect screenshots and practice this flow. Choose two eligible Cardiology providers with visible component differences. Do not claim a browser or PostgreSQL pass until you have run them. This script describes intended live behavior, not a recording.

## 0:00–0:20 — Overview

“CareRank Lab is an independent portfolio project built with fictional provider and encounter data. The engineering problem is making a ranking explainable: who can be scored, what contributes to a score, and what evidence is missing. It is not a clinical recommendation system or a reproduction of Garner's methodology.”

Action: show the provider/encounter totals, evidence threshold and pipeline status.

## 0:20–0:55 — Analytics

Action: click Explore analytics. Keep Cardiology selected. Hover a point, then open its profile and return using Analytics navigation.

“This view includes every eligible provider in one specialty, not just a search page. Horizontal position is raw average encounter cost; vertical position is a simulated heuristic score. Diamonds are strictly above the cohort mean score and below its mean cost. That is a descriptive filter, not proof of better care. The actual cost component adjusts for simulated procedure and risk mix.”

## 0:55–1:15 — Evidence

Action: scroll to eligibility and completeness.

“Missing evidence is different from poor outcomes. These exclusion categories are mutually exclusive: fewer than 30 observed outcomes takes precedence, then low completeness. Providers without encounters and providers not processed are separately identified. Totals reconcile, and completeness uses exact counts rather than rounded display values.”

## 1:15–1:40 — Compare

Action: Provider Explorer → Cardiology → select two providers → Compare.

“The grouped bars show component tradeoffs on the same scale. Outcome gets 60 percent, cost 25, reliability 10 and volume 5. Ten more outcome-component points contribute six weighted points; ten more cost-component points contribute 2.5. The detailed evidence stays visible below.”

## 1:40–2:00 — Engineering and ownership

“FastAPI reads materialized provider scores; PostgreSQL performs cohort aggregates. Encounter records never reach the browser. The UI handles stale requests and offers keyboard navigation and data tables. AI assisted the implementation and documentation. I am learning to maintain it by tracing each graph to its query and testing boundary cases. My verification report separates passed checks from the PostgreSQL and browser checks still needing local execution.”

If you have subsequently passed local checks, replace the last sentence with the exact checks and date. Never imply these synthetic scores establish clinical superiority.

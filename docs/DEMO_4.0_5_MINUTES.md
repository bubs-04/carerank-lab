# CareRank 4.0 — five-minute technical demonstration

Use an isolated development demonstration instance backed by `carerank_test`. Never demonstrate lifecycle writes against history that must remain unchanged. Complete migration 005, prepare synthetic ranking data and registry fixtures A/B, and provision distinct Viewer, Analyst and Administrator accounts using the development-only CLI. Keep passwords out of the shared screen and terminal history. Use a second browser context for the viewer. See [README](../README.md) for commands and [executed verification](VERIFICATION_4.0.md) for the tested environment.

## 0:00–0:45 — authentication and trust boundary

Open the signed-out application. Explain that provider data, registry history and incident evidence require authentication. Sign in as Viewer. Show the account role and then the existing synthetic overview: fictional providers and encounters remain separate from public registry identities. Explain that the server holds the session and authorization state; there is no role or bearer token in localStorage.

## 0:45–1:30 — evidence and least privilege

Open Data operations, select **Deterministic fixture (test data)**, and open **Quality monitoring**. Show severity/status/assignment filters, the unresolved queue, and one alert's evidence. The intentional fixture warnings are expected. Show the recorded threshold, observed value, snapshot/run reference and original creation event. The Viewer can inspect evidence but has no action form. An API request with a valid Viewer session cannot perform an analyst action even if the frontend is bypassed.

## 1:30–2:45 — authenticated analyst workflow

Sign in as Analyst. Open an unassigned open incident. Assign it to an active analyst and record an acknowledgement with a concrete note, such as “Confirmed missing specialty in the captured fixture; reviewing source records.” Move it to investigating and inspect the exact run findings or snapshot records. Return to the monitoring queue, resolve it with the decision and reason, then reopen it with a follow-up note. Show the timeline's authenticated actor, timestamp, previous/new state and assignment changes. Explain that resolution does not rewrite the original failed rule evaluation.

## 2:45–3:30 — conflict and session protection

Open the same incident in two tabs before updating it. Save a decision in the first tab, then try the second tab's older revision. Show the conflict message and refresh/review path; neither the state nor the decision history is silently overwritten. Sign out. Reload a protected view and show that the server session is revoked. Describe exact-origin and CSRF checks on mutations and database-backed login throttling; do not deliberately exhaust the demonstration account's login limit.

## 3:30–4:15 — administration and preservation

Sign in as Administrator. Show account role/activation management and security history if using the administration interface, or the documented protected account endpoints. Explain that account changes require the reviewed revision, revoke sessions and cannot remove the last active administrator. Use two administration tabs to show a stale role/activation change rejected with 409, followed by refreshed controls and a deliberate retry; stale forms cannot restore revoked access. Historical 3.1 CLI labels remain explicitly unauthenticated; 4.0 web actions carry stable account references. Show the migration preservation evidence for snapshots, synthetic data, alerts and old audit events.

## 4:15–5:00 — architecture and verification

Open [the architecture diagrams](ARCHITECTURE_4.0.md). Walk through the trusted proxy overwriting client addresses, separate account/source limits with bounded state, authentication, transaction/revision checks and atomic audit insertion. Point out the restricted API database role and separate migration credentials. Point to actual backend, React, production-build and Chromium results in [VERIFICATION_4.0.md](VERIFICATION_4.0.md), including negative security checks. State remaining limits: local development provisioning, no SSO/MFA or production account recovery, no multi-tenant model, and privileged database administrators can alter schema. Close with the draft PR and review scope; no production deployment is implied.

The demo may change only the disposable test database. Do not display passwords, raw session cookies, CSRF values or database connection URLs while sharing the screen.

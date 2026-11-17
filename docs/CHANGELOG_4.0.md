# CareRank 4.0 changelog

Based on merged CareRank 3.1, PR #3, latest `main` at `ce4daa4`.

- Added salted scrypt passwords and opaque, expiring server-side sessions with login, session restoration and logout.
- Added backend-enforced Administrator, Analyst and Viewer roles across protected application data and incident actions.
- Added development-only account provisioning with interactive/stdin passwords and no shipped account credentials.
- Added persistent login throttling, exact-origin validation, session-bound CSRF tokens and safe cookie configuration.
- Added authenticated web incident acknowledgement, investigation, assignment, resolution and reopening with required decision notes and optimistic revision checks.
- Added durable authenticated identity references and prior-assignment details to investigation audit history; retained historical system/CLI attribution.
- Added administrator account role/activation controls with session revocation and security events.
- Added migration 004 without replacing synthetic data, registry snapshots, alerts or existing audit events.
- Updated the React workspace with sign-in, session expiration handling, logout, analyst queues, role-aware controls and actionable errors.
- Changed Compose startup to seed only pristine synthetic data; explicit pipeline execution still replaces synthetic data by design.
- Added negative security tests, role-aware browser workflows, architecture diagrams, threat model, operations guidance and a five-minute demonstration.

No public deployment, repository visibility change or production compliance claim is included. Current test results and limitations are recorded in [VERIFICATION_4.0.md](VERIFICATION_4.0.md).

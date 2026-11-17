# CareRank 4.0 security review corrections

The independent review covered `db17958bc16211853a4c042aae0df46640ef2f4b` on existing PR #4. This revision corrects the three confirmed defects and separates local runtime database authority. It does not merge, deploy or certify the application. The updated source commit, executed results and any unresolved checks belong in [VERIFICATION_4.0.md](VERIFICATION_4.0.md); the descriptions below are implementation and regression mappings.

## 1. Stale administrator updates restored revoked access

The Administration form cached both role and activation and submitted both values. The API had no target-account version precondition, so a later submission could overwrite another administrator’s revocation with stale values.

Migration 005 adds a non-null positive account revision, initialized to 1 for existing accounts. `PATCH /api/auth/users/{id}` requires `expected_revision` plus at least one non-null changed access field. The transaction takes the shared security lock, rechecks the acting account/session/role, locks the target account and compares the reviewed revision. A mismatch returns 409 without updating state. Successful changes increment the revision and atomically commit account state, affected-session deletion and an audit event containing prior/new role, activation and revision. The existing last-active-administrator check remains inside the lock.

React submits only intentionally changed fields. A typed HTTP error makes 409 handling reliable, and the form reloads the account without automatically retrying. The form key includes the durable revision so a batched fetch/refresh cannot retain old local controls. The administrator must review and deliberately resubmit.

Regression coverage in `backend/tests/test_security.py` includes interleaved administrators attempting to restore a revoked role/reactivate a disabled account, administrator revocation during an already authorized request, concurrent last-administrator modifications, required revision/intent, unauthorized and CSRF-invalid account changes, and rollback of account/session changes when a real audit insertion fails. `frontend/src/Administration.test.tsx` covers selective fields, conflict reload, revoked-role/disabled-state refresh, deliberate retry with the new revision and failed refresh.

## 2. One proxy address collapsed unrelated login budgets

The API used its socket peer for source throttling. Behind Nginx/Vite this was the shared proxy address, so one client could exhaust a source budget used by unrelated clients.

The proxies now overwrite `X-CareRank-Client-IP` from the incoming socket and strip other forwarding headers. The API accepts the dedicated value only from an explicit trusted immediate peer, rejects missing/malformed/chained/scoped values from that peer, and ignores caller forwarding input from all other sources. IPv4-mapped IPv6 normalizes to IPv4. Uvicorn retains `--no-proxy-headers`.

Compose publishes only the web port and places Nginx/API on an internal proxy network. The only trusted proxy is Nginx’s fixed `172.30.84.3/32` address. Native/cloud Vite explicitly trusts loopback within the local operator boundary. Account limits remain independent of source identity: 10 attempts per normalized username and 30 per source in 15 minutes, including successful sign-ins.

Backend regressions prove trusted/untrusted header behavior and independent source/account budgets. `scripts/verify_proxy_security.py` exercises the shipped Nginx configuration with two real Docker clients: one exhausts its budget and cannot escape with forged headers; the other can authenticate through the same proxy. CI runs this against the restricted API connected to `carerank_test`.

Real users behind a common NAT still share a source address. Host/Docker administrators and trusted proxy operators remain privileged. Shared/public deployments must validate their actual proxy chain, private API connectivity, exact trust list and TLS boundary.

## 3. Blocked requests allocated unbounded username rows

The old limiter continued processing source and username buckets after discovering a blocked source. Arbitrary usernames on denied requests therefore allocated additional persistent records, while expiry cleanup could delete an unbounded set.

The limiter now checks the source first and returns 429 before username lookup, allocation, row counting or cleanup when that source is exhausted. New allocations run under the shared PostgreSQL advisory lock. An allocation ceiling of 10,000 buckets prevents further insertion at capacity; live limits are never evicted to admit new clients. Expiry cleanup uses the new `(window_start, key)` index and deletes at most 100 expired buckets per allocation attempt. Exhausted account attempts consume the permitted source budget, bounding repeated account probes too.

Regressions prove that 100 blocked requests with new usernames perform only the indexed source lookup without growth or cleanup; simultaneous connections cannot exceed a small configured test ceiling; and expiry cleanup is indexed, bounded and preserves live limits. Migration 005 preserves existing throttle rows. A legacy table already above the ceiling cannot grow through this path and shrinks through bounded expiry cleanup, rather than erasing active security windows.

Fail-closed capacity deliberately favors preserving brute-force limits over admitting unknown sources when full. Distributed exhaustion and contention on the shared security-write lock remain availability risks. Gateway limits, monitoring and production load testing remain required.

## Database authority and migration preservation

Compose now generates distinct owner/runtime secrets and provisions `carerank_api` through the separate `runtime` operator service. `app.runtime_role` requires the same target database and different login/password, rejects privileged/owning/inherited roles, and applies explicit grants. The API can read domain data and update only supported account/incident state, append audit events and maintain sessions/limits. It cannot alter schema, create accounts, change password hashes, ingest/replace datasets or update/delete audit rows. Tests exercise positive application permissions and negative owner/destructive operations.

CI administers only `carerank_test` with owner credentials, then serves browser tests using a restricted runtime role. The cloud helper applies the same separation and removes owner/test credential variables from API/frontend processes. Its anonymous provider readiness check requires 401. These environment helper changes are outside the repository; source setup/launcher changes preserve existing passwords and were not run against a Mac database.

Migration 005 is additive and leaves applied migrations 001–004 unchanged. It preserves existing account, session, synthetic, registry, alert and audit records. Retained databases upgrade forward; downgrade is allowed only for disposable `carerank_test` resets. Preservation regressions compare all pre-existing table columns before/after 004→005. Main-database preservation evidence is recorded separately in the verification report.

## Review and deployment gate

Request a fresh independent security review of the corrected PR head before merge. Local regression results do not replace that review. Shared/public deployment also remains blocked on deployment-specific secret delivery/rotation separating runtime and owner authority, managed TLS/proxy configuration, production identity lifecycle/recovery, backup/restore and retention, operational monitoring, load/capacity testing and external audit-tamper protections where required. CareRank has no enterprise SSO/MFA or multi-tenant boundary and makes no patient-data or compliance certification claim.

# CareRank 4.0 architecture

CareRank 4.0 extends the merged 3.1 system with authenticated analyst operations. Authentication and incident decisions run in FastAPI; React displays the permissions and server responses. Existing synthetic and registry processing remain separate operator workflows.

![CareRank 4.0 trust boundaries and authenticated workflow](architecture_4.0.svg)

```mermaid
flowchart TB
  Browser[React workspace: sign-in, queue, evidence, timeline]
  Proxy[Same-origin proxy: overwrite client IP; API trusts explicit peer]
  Auth[Authentication: opaque cookie, active account, absolute expiry]
  Read[Protected ranking, analytics and registry GET routes]
  Guard[Mutation guard: exact Origin + CSRF + backend role]
  Actions[Incident action transaction: lock, recheck identity and revision]
  Admin[Account transaction: lock + identity recheck + expected account revision]
  Runtime[Restricted API database login]
  DB[(PostgreSQL 16)]
  CLI[Development provisioning / ingestion / evaluation CLI]
  Browser --> Proxy --> Auth
  Auth --> Read --> Runtime
  Auth --> Guard
  Guard --> Actions --> Runtime
  Guard --> Admin --> Runtime
  Runtime --> DB
  CLI -->|separate owner credentials| DB
```

## Boundaries and data model

Migration 004 adds `auth_users`, `auth_sessions`, `auth_login_limits` and `auth_events`. Nullable references attach authenticated actor and assignment identity to monitoring history without rewriting legacy events. Existing `assigned_to` text remains readable for historical CLI assignments. New web assignments resolve to active Analyst or Administrator accounts. Migration 005 adds the durable `auth_users.revision` precondition and `(window_start, key)` login-expiry index. It preserves existing rows and refuses downgrade outside `carerank_test`.

```mermaid
erDiagram
  AUTH_USERS ||--o{ AUTH_SESSIONS : authenticates
  AUTH_USERS ||--o{ AUTH_EVENTS : actor_or_subject
  AUTH_USERS o|--o{ MONITOR_ALERTS : assigned_user
  AUTH_USERS o|--o{ MONITOR_EVENTS : actor_or_assignment
  REGISTRY_RUNS ||--o{ MONITOR_EVALUATIONS : measured_by
  MONITOR_RULES ||--o{ MONITOR_EVALUATIONS : defines
  MONITOR_EVALUATIONS ||--o| MONITOR_ALERTS : raises
  MONITOR_ALERTS ||--o{ MONITOR_EVENTS : audited_by
```

Synthetic providers, encounters and scores are not joined to registry clinicians or user accounts. Monitoring retains stable references to the existing run, rule and evaluation that produced the alert. An investigation changes workflow state; it does not rewrite a failed rule result or replace snapshot evidence.

## Request flow

1. The browser submits credentials to the same-origin login endpoint. Nginx/Vite overwrites the dedicated client-IP header from the incoming socket. The API accepts that header only from an explicit trusted immediate proxy, normalizes equivalent IP forms, and otherwise uses the socket peer. It checks the exact allowed origin, independent persistent account/source limits, active account and scrypt hash. Blocked sources return before username allocation; indexed expiry cleanup and a serialized allocation ceiling bound throttle state.
2. Successful login generates a fresh random session token. The database stores its SHA-256 digest, account reference, CSRF token and absolute expiry. The browser receives an HttpOnly, SameSite cookie; Secure is enabled by default.
3. `/api/auth/me` restores the user and CSRF token. All application reads resolve the active account and unexpired session server-side.
4. An analyst submits a decision with `expected_revision`, a required note, an optional allowed next state and optional assignment. The server checks CSRF and role, then verifies current authorization/revision under transaction locks.
5. The alert update and append-only event commit together. The event carries authenticated actor ID, timestamp, old/new state, prior/new assignment and decision note. Conflicting revisions are rejected for review, rather than silently retried.
6. An administrator submits an account PATCH containing `expected_revision` and changed fields only. Inside the locked transaction the API rechecks acting identity and target revision, protects the last active administrator, increments the revision, revokes affected sessions and appends prior/new access state. These writes commit atomically. A conflict reloads the form for deliberate review, including resetting cached local controls when the account revision changes.
7. Logout deletes the server session. Role/activation changes revoke affected sessions, so changing a frontend variable cannot retain authority.

```mermaid
sequenceDiagram
  actor Analyst
  participant UI as React
  participant API as FastAPI
  participant DB as PostgreSQL
  Analyst->>UI: Decision note + action
  UI->>API: POST action + session cookie + CSRF + expected revision
  API->>API: Origin / session / role validation
  API->>DB: Begin; lock and recheck account/session/alert
  alt Revision is current
    API->>DB: Update alert; append identity-linked audit
    DB-->>API: Commit
    API-->>UI: New revision
    UI-->>Analyst: Reload queue and timeline
  else Revision changed
    API-->>UI: 409 conflict
    UI-->>Analyst: Refresh and review before retry
  end
```

## Runtime and operations

The API uses server-side sessions rather than long-lived browser JWTs, keeping logout and account revocation immediate. Auth writes use READ COMMITTED transactions with explicit locking; analytical reads retain existing repeatable-read behavior. Passwords and raw session tokens never appear in API responses or audit decisions.

Compose remains a localhost development topology, with a non-root API container and unpublished API/database ports. A separate frontend network carries the localhost web port. Its internal proxy network reserves Nginx outside the dynamic address pool, with a fixed Nginx address (`172.30.84.3/32`) as the API’s only trusted proxy; unrelated client containers receive distinct source budgets through the same Nginx. Nginx replaces forwarding input rather than appending it. Uvicorn forwarding remains disabled. Its bootstrap seeds only a pristine synthetic lab; explicit pipeline commands remain replacement tools. Provisioning is a development-only CLI; there is no open registration or bootstrap password.

Compose, CI and cloud development now run the API with a restricted role; migrations, provisioning and ingestion retain separate operator credentials. The `runtime` Compose service runs `app.runtime_role` after migration/seed to provision explicit grants, and CI repeats that separation for `carerank_test`. Native development configures the same two URLs explicitly. The cloud startup helper is an environment asset, updated for runtime credential separation and a 401 protected readiness check. See [the threat model and deployment blockers](SECURITY_4.0.md).

## Verification boundary

Backend tests exercise authorization and database transactions. Component tests exercise login/session and action states. Browser tests exercise the actual same-origin application and use a separate API bound to `carerank_test` for writes. Migration preservation checks compare existing columns and row counts/content before and after upgrade. Runtime-permission tests and a two-client Docker/Nginx probe exercise boundaries beyond React. See [executed evidence](VERIFICATION_4.0.md); diagrams describe the design and are not test results.

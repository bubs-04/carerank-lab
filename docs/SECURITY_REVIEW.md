# Basic Security Review

Scope: source review plus parameter validation, injection-shaped search, rollback and API tests. This is not a penetration test or a compliance certification.

| Area | Implemented | Remaining work |
|---|---|---|
| Data | Fictional ranking records plus a separate public CMS registry; no patient records or identity-to-score joins | Do not replace data with PHI without a governed architecture |
| SQL | ORM-bound filter parameters, escaped literal search wildcards, static aggregation SQL | Production query budgets and statement timeouts |
| Input | Pydantic strict batch schemas; finite risk/cost; API bounds; comparison rules | Rate limits and abuse protection |
| Secrets | Environment configuration, random local password, gitignore, no browser credential injection | Managed secrets and rotation |
| Network | Compose host ports bind localhost; database has no published port | TLS and authenticated ingress before remote exposure |
| UI | React escaping; no raw HTML injection; Nginx headers and CSP | Browser accessibility/security audit |
| Operations | Non-root API and web containers; independent failure audit; atomic writes | Separate read-only DB role for API, backups, monitoring, disaster recovery |
| Dependencies | Python direct pins and npm lockfile | Automated vulnerability scanning and periodic updates |

The local demo has no authentication. The Compose API and pipeline use the same database account; API endpoints are read-only but the account is not least-privilege. This is an explicit production gap. A crash or lost database connection can leave an audit row at `running`; ordinary exceptions are recorded as failed with a sanitized error class. Raw exception details are not sent to API clients. The pipeline CLI intentionally replaces all demo provider/event/score records, so run it only against a dedicated demo database.

Review finding fixed during implementation: request reads use a repeatable-read transaction, so a count and paginated results cannot observe two versions of the dataset during a concurrent refresh. Pipeline writes stay read committed and use a transaction-scoped advisory lock. No claim is made of tested high concurrency, HIPAA compliance, clinical safety, or externally audited security.

## CareRank 3.1 review

Eight monitoring routes are GET-only. Attempting POST/PATCH/PUT/DELETE on alert detail returns 405; HTTP headers cannot supply an actor. Investigation uses a local CLI with explicit self-reported operator label, bounded notes, validated transitions and expected revision. A transaction commits the alert state and one audit event together. PostgreSQL/SQLite migration triggers prohibit updating/deleting audit events; a privileged database administrator can still alter the schema, so this is not tamper-proof storage.

Rule observations derive only from stored registry facts. Logs omit database exception text and emit safe exception classes. Profile/evaluation and alert uniqueness constraints plus a short PostgreSQL advisory lock protect reruns; PostgreSQL behavior still requires the documented local/CI checks. No external alert notifications are sent. Existing Docker ports remain loopback-only. A real deployment still requires authentication, authorization, distinct database roles, TLS, backups and operational monitoring; none is implied by this local release.

-- Run as schema owner/administrator after migration 004, against the intended DB.
-- psql -v ON_ERROR_STOP=1 -v runtime_role=carerank_api -d carerank -f docs/runtime-grants.sql
-- Create this LOGIN role separately with a prompted secret. No credentials belong here.
\set ON_ERROR_STOP on
SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role') AS role_exists \gset
\if :role_exists
\else
  \echo 'Create the dedicated runtime login role before applying grants.'
  \quit 1
\endif
SELECT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role'
  AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
) OR EXISTS (
  SELECT 1 FROM pg_class WHERE relowner = (SELECT oid FROM pg_roles WHERE rolname = :'runtime_role')
) OR EXISTS (
  SELECT 1 FROM pg_namespace WHERE nspowner = (SELECT oid FROM pg_roles WHERE rolname = :'runtime_role')
) OR EXISTS (
  SELECT 1 FROM pg_database WHERE datdba = (SELECT oid FROM pg_roles WHERE rolname = :'runtime_role')
) OR EXISTS (
  SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = :'runtime_role')
) AS role_unsafe \gset
\if :role_unsafe
  \echo 'Refusing an owning, privileged or inherited runtime role.'
  \quit 1
\endif

BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"runtime_role";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"runtime_role";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM :"runtime_role";
GRANT CONNECT ON DATABASE :"DBNAME" TO :"runtime_role";
GRANT USAGE ON SCHEMA public TO :"runtime_role";
GRANT SELECT ON providers, encounters, scores, pipeline_runs,
  registry_sources, registry_snapshots, registry_runs, registry_records,
  registry_changes, registry_findings, monitor_rules, monitor_evaluations
  TO :"runtime_role";
GRANT SELECT ON monitor_alerts TO :"runtime_role";
GRANT UPDATE (status, assigned_to, assigned_user_id, resolution, revision, updated_at)
  ON monitor_alerts TO :"runtime_role";
GRANT SELECT, INSERT ON monitor_events, auth_events TO :"runtime_role";
GRANT SELECT ON auth_users TO :"runtime_role";
GRANT UPDATE (role, active) ON auth_users TO :"runtime_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions, auth_login_limits TO :"runtime_role";
COMMIT;

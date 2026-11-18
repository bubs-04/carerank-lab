"""Provision least-privilege API and worker roles using an administrator connection.

Run after migrations with DATABASE_URL (owner), RUNTIME_DATABASE_URL (API), and
optional WORKER_DATABASE_URL (worker). All credentials must be distinct.
Passwords are never logged. This command is an operator task, never API startup.
"""

import os
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

READ_TABLES = (
    "providers",
    "encounters",
    "scores",
    "pipeline_runs",
    "registry_sources",
    "registry_snapshots",
    "registry_runs",
    "registry_records",
    "registry_changes",
    "registry_findings",
    "monitor_rules",
    "monitor_evaluations",
)


def provision(owner_url: str, runtime_url: str, worker: bool = False):
    owner, runtime = make_url(owner_url), make_url(runtime_url)
    if owner.drivername != "postgresql+psycopg" or runtime.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL psycopg URLs required")
    if (owner.host, owner.port or 5432, owner.database) != (
        runtime.host,
        runtime.port or 5432,
        runtime.database,
    ) or owner.query != runtime.query:
        raise ValueError("Owner and runtime connections must address the same database")
    if not runtime.username or runtime.username == owner.username or not runtime.password:
        raise ValueError("A distinct runtime login and password are required")
    if len(runtime.username.encode()) > 63 or len(runtime.password) < 24:
        raise ValueError("Runtime role name or password does not meet requirements")
    if runtime.password == owner.password:
        raise ValueError("Runtime and owner passwords must differ")
    role = sql.Identifier(runtime.username)
    # Raw psycopg avoids including password-bearing DDL in SQLAlchemy exception logs.
    with psycopg.connect(owner.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
        db.execute("SELECT pg_advisory_xact_lock(721408)")
        existing = db.execute(
            "SELECT oid, rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
            "FROM pg_roles WHERE rolname = %s",
            (runtime.username,),
        ).fetchone()
        if existing:
            oid, privileged = existing
            owns_or_inherits = db.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_class WHERE relowner = %s) "
                "OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = %s) "
                "OR EXISTS (SELECT 1 FROM pg_database WHERE datdba = %s) "
                "OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = %s)",
                (oid, oid, oid, oid),
            ).fetchone()[0]
            if privileged or owns_or_inherits:
                raise ValueError("Refusing an owning, privileged or inherited runtime role")
        else:
            db.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(role))
        db.execute(
            sql.SQL("ALTER ROLE {} LOGIN NOINHERIT PASSWORD {}").format(role, sql.Literal(runtime.password))
        )
        # Table-level REVOKE does not remove column ACLs. Clear those as well
        # before assigning a role's current responsibilities (including upgrades).
        columns = db.execute(
            "SELECT c.relname, array_agg(a.attname ORDER BY a.attnum) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped "
            "AND a.attacl IS NOT NULL GROUP BY c.relname"
        ).fetchall()
        for table, names in columns:
            db.execute(
                sql.SQL("REVOKE ALL ({}) ON TABLE public.{} FROM {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, names)), sql.Identifier(table), role
                )
            )
        statements = [
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}"),
            sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}"),
            sql.SQL("REVOKE ALL ON SCHEMA public FROM {}"),
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}"),
            sql.SQL("GRANT SELECT ON " + ", ".join(READ_TABLES) + " TO {}"),
            sql.SQL("GRANT SELECT ON monitor_alerts TO {}"),
            sql.SQL(
                "GRANT UPDATE (status, assigned_to, assigned_user_id, resolution, revision, updated_at) "
                "ON monitor_alerts TO {}"
            ),
            sql.SQL("GRANT SELECT, INSERT ON monitor_events, auth_events TO {}"),
            sql.SQL("GRANT SELECT ON auth_users TO {}"),
            sql.SQL("GRANT UPDATE (role, active, revision) ON auth_users TO {}"),
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions, auth_login_limits TO {}"),
        ]
        if worker:
            # Workers can publish registry/monitoring evidence, but cannot administer
            # identities, synthetic data, schema or append-only audit history.
            statements = statements[:4] + [
                sql.SQL(
                    "GRANT SELECT ON registry_sources, registry_snapshots, registry_runs, registry_records, registry_findings, registry_changes, monitor_rules, monitor_evaluations, monitor_alerts, monitor_events, pipeline_definitions, pipeline_executions, pipeline_attempts, pipeline_events TO {}"
                ),
                sql.SQL(
                    "GRANT INSERT ON registry_sources, registry_snapshots, registry_runs, registry_records, registry_findings, registry_changes, monitor_rules, monitor_evaluations, monitor_alerts, monitor_events, pipeline_executions, pipeline_attempts, pipeline_events TO {}"
                ),
                sql.SQL("GRANT UPDATE ON registry_runs, pipeline_executions, pipeline_attempts TO {}"),
                sql.SQL("GRANT UPDATE (next_run_at) ON pipeline_definitions TO {}"),
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE registry_findings_id_seq TO {}"),
            ]
        else:
            statements += [
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON pipeline_definitions TO {}"),
                sql.SQL("GRANT SELECT, INSERT ON pipeline_executions TO {}"),
                sql.SQL(
                    "GRANT UPDATE (status, revision, finished_at, error_code, lease_expires_at) ON pipeline_executions TO {}"
                ),
                sql.SQL("GRANT SELECT ON pipeline_attempts TO {}"),
                sql.SQL("GRANT UPDATE (status, finished_at, error_code) ON pipeline_attempts TO {}"),
                sql.SQL("GRANT SELECT, INSERT ON pipeline_events TO {}"),
            ]
        db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        db.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(runtime.database), role)
        )
        for statement in statements:
            db.execute(statement.format(role))


def main():
    try:
        if os.environ.get("WORKER_DATABASE_URL"):
            owner = make_url(os.environ["DATABASE_URL"])
            api = make_url(os.environ["RUNTIME_DATABASE_URL"])
            worker = make_url(os.environ["WORKER_DATABASE_URL"])
            if worker.username == api.username or worker.password in {owner.password, api.password}:
                raise ValueError("Worker, API and owner require distinct logins and passwords")
            provision(os.environ["DATABASE_URL"], os.environ["WORKER_DATABASE_URL"], worker=True)
        provision(os.environ["DATABASE_URL"], os.environ["RUNTIME_DATABASE_URL"])
    except (KeyError, ValueError, ArgumentError, psycopg.Error):
        # PostgreSQL errors can include the password-bearing ALTER ROLE statement.
        print(
            "Runtime role setup failed; verify distinct credentials, database target, role safety and migrations.",
            file=sys.stderr,
        )
        return 1
    print("Least-privilege runtime role provisioned; owner credentials remain with operator tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Provision the least-privilege API role using a separate administrator connection.

Run after migrations with DATABASE_URL (owner) and RUNTIME_DATABASE_URL (API).
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


def provision(owner_url: str, runtime_url: str):
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
        db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        db.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(runtime.database), role)
        )
        for statement in statements:
            db.execute(statement.format(role))


def main():
    try:
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

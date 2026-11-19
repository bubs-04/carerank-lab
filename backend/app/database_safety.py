"""Fail-closed connection identity checks for migrations and destructive tooling."""

import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import make_url

# Do not allow libpq service/hostaddr/dbname/user/options to override URL identity.
# These transport-only options do not change the selected database/login/server.
TRANSPORT_OPTIONS = {"sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout", "application_name"}
ROUTING_ENV = {
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGOPTIONS",
    "PGTARGETSESSIONATTRS",
    "PGLOADBALANCEHOSTS",
}


def postgres_configuration(url, *, database=None, user=None, hosts=None):
    url = make_url(url)
    if (
        url.get_backend_name() != "postgresql"
        or not url.database
        or not url.username
        or not url.host
        or "," in url.host
        or (database is not None and url.database != database)
        or (user is not None and url.username != user)
        or (hosts is not None and url.host not in hosts)
        or set(url.query) - TRANSPORT_OPTIONS
        or any(not isinstance(value, str) for value in url.query.values())
        or any(os.environ.get(key) for key in ROUTING_ENV)
    ):
        raise ValueError("Unsafe or ambiguous PostgreSQL connection configuration")
    return url


def postgres_connection(connection, *, database=None, user=None, hosts=None):
    """Check on the very connection/transaction that will perform the operation."""
    url = postgres_configuration(connection.engine.url, database=database, user=user, hosts=hosts)
    actual_database, current_user, session_user = connection.execute(
        text("SELECT current_database(), current_user, session_user")
    ).one()
    if (actual_database, current_user, session_user) != (url.database, url.username, url.username):
        raise ValueError("PostgreSQL connected database or user differs from the approved target")


def disposable_connection(connection):
    if connection.dialect.name == "postgresql":
        postgres_connection(connection, database="carerank_test")
        return
    url = connection.engine.url
    if (
        connection.dialect.name == "sqlite"
        and not url.query
        and Path(url.database or "").name == "carerank_test"
    ):
        actual = {row[1]: row[2] for row in connection.exec_driver_sql("PRAGMA database_list")}
        if actual.get("main") and Path(actual["main"]).resolve() == Path(url.database).resolve():
            return
    raise ValueError("Destructive operation requires the connected disposable carerank_test database")

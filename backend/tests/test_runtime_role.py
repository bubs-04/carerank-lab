"""Prove API permissions with a real restricted PostgreSQL connection."""

import os
import secrets
import uuid

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

from app.runtime_role import provision


def test_runtime_configuration_rejects_wrong_target_or_shared_credentials():
    owner = "postgresql+psycopg://owner:long-owner-secret-value-012345@localhost/carerank_test"
    for runtime in (
        "postgresql+psycopg://runtime:long-runtime-secret-012345@localhost/carerank",
        "postgresql+psycopg://owner:long-runtime-secret-012345@localhost/carerank_test",
        "postgresql+psycopg://runtime:long-owner-secret-value-012345@localhost/carerank_test",
        "postgresql+psycopg://runtime:short@localhost/carerank_test",
    ):
        with pytest.raises(ValueError):
            provision(owner, runtime)


@pytest.fixture(scope="module")
def runtime_connection():
    owner_url = os.environ.get("TEST_DATABASE_URL")
    if not owner_url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL carerank_test")
    owner = make_url(owner_url)
    if owner.get_backend_name() != "postgresql" or owner.database != "carerank_test":
        pytest.fail("Runtime permission tests require PostgreSQL database carerank_test")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = owner_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    username = "carerank_boundary_" + uuid.uuid4().hex[:16]
    runtime = owner.set(username=username, password=secrets.token_hex(24))
    try:
        provision(owner_url, runtime.render_as_string(hide_password=False))
        # Reapplying after a migration must be safe and deterministic.
        provision(owner_url, runtime.render_as_string(hide_password=False))
        with psycopg.connect(
            runtime.set(drivername="postgresql").render_as_string(hide_password=False)
        ) as db:
            yield db
    finally:
        with psycopg.connect(owner.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(username)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(username)))


def test_runtime_can_read_and_write_only_application_columns(runtime_connection):
    db = runtime_connection
    assert db.execute(
        "SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls) "
        "FROM pg_roles WHERE rolname = current_user"
    ).fetchone() == (True,)
    db.execute("SELECT * FROM providers LIMIT 1")
    db.execute("SELECT * FROM monitor_alerts WHERE false FOR UPDATE")
    db.execute("SELECT * FROM auth_users WHERE false FOR UPDATE")
    db.execute("UPDATE auth_users SET role = 'viewer', active = false, revision = revision + 1 WHERE false")
    db.execute("UPDATE monitor_alerts SET status = 'open', revision = revision + 1 WHERE false")
    db.execute(
        "INSERT INTO auth_events (id, action, details, created_at) VALUES (%s, %s, '{}'::jsonb, now())",
        (str(uuid.uuid4()), "permission_test"),
    )
    db.rollback()  # Prove permission without retaining a fabricated application event.


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.runtime_must_not_create (id integer)",
        "ALTER TABLE auth_users ADD COLUMN runtime_must_not_alter integer",
        "TRUNCATE providers CASCADE",
        "DELETE FROM providers WHERE false",
        "UPDATE registry_records SET accepted = false WHERE false",
        "UPDATE auth_users SET password_hash = 'tampered' WHERE false",
        "INSERT INTO auth_users DEFAULT VALUES",
        "DELETE FROM auth_users WHERE false",
        "UPDATE auth_events SET action = 'tampered' WHERE false",
        "DELETE FROM auth_events WHERE false",
        "DELETE FROM monitor_events WHERE false",
        "DELETE FROM monitor_alerts WHERE false",
        "UPDATE monitor_alerts SET severity = 'critical' WHERE false",
    ],
)
def test_runtime_denies_owner_and_destructive_operations(runtime_connection, statement):
    db = runtime_connection
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(statement)
    finally:
        db.rollback()

"""Real misrouting uses only a fresh disposable shadow DB, never retained data."""

import importlib.util
import os
import uuid
from pathlib import Path
import psycopg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text
from app.database_safety import postgres_configuration, postgres_connection
from app.demo import prepare, guarded_demo
from test_observability import prepare_telemetry_database


@pytest.mark.parametrize(
    "override",
    [
        "dbname=carerank_shadow_test",
        "host=elsewhere",
        "hostaddr=127.0.0.2",
        "port=5433",
        "user=another_user",
        "service=hidden",
        "options=-c%20role%3Dother",
        "connect_timeout=1&connect_timeout=2",
    ],
)
def test_routing_overrides_rejected_before_connection(override):
    engine = create_engine(
        "postgresql+psycopg://test_owner@127.0.0.1/carerank_test?" + override,
        creator=lambda: pytest.fail("Unsafe configuration opened a connection"),
    )
    with pytest.raises(ValueError, match="Unsafe"):
        prepare_telemetry_database(engine)
    engine.dispose()


@pytest.mark.parametrize("name", ["PGSERVICE", "PGHOSTADDR", "PGDATABASE", "PGUSER", "PGOPTIONS"])
def test_inherited_libpq_routing_rejected(monkeypatch, name):
    monkeypatch.setenv(name, "unapproved-override")
    with pytest.raises(ValueError, match="Unsafe"):
        postgres_configuration("postgresql+psycopg://test_owner@127.0.0.1/carerank_test")


@pytest.fixture(scope="module")
def shadow_database():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Requires disposable PostgreSQL carerank_test")
    target = postgres_configuration(raw, database="carerank_test")
    admin = create_engine(target, isolation_level="AUTOCOMMIT")
    name = "carerank_guard_" + uuid.uuid4().hex[:16]
    shadow = None
    created = False
    try:
        with admin.connect() as connection:
            postgres_connection(connection, database="carerank_test")
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        shadow = create_engine(target.set(database=name))
        with shadow.begin() as connection:
            postgres_connection(connection, database=name)
            connection.exec_driver_sql("CREATE TABLE guard_sentinel (id integer PRIMARY KEY, value text)")
            connection.exec_driver_sql(
                "INSERT INTO guard_sentinel VALUES (1, 'retain this disposable sentinel')"
            )
        yield target, shadow
    finally:
        if shadow:
            shadow.dispose()
        if created:
            with admin.connect() as connection:
                postgres_connection(connection, database="carerank_test")
                # Only the random database created by this fixture is removed.
                assert name.startswith("carerank_guard_") and len(name) == 31
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


def mismatched_engine(target, shadow, **overrides):
    actual = shadow.url.set(drivername="postgresql").render_as_string(hide_password=False)
    return create_engine(target.set(**overrides), creator=lambda: psycopg.connect(actual))


def assert_sentinel_intact(shadow):
    with shadow.connect() as connection:
        assert inspect(connection).get_table_names() == ["guard_sentinel"]
        assert connection.execute(text("SELECT * FROM guard_sentinel")).all() == [
            (1, "retain this disposable sentinel")
        ]


def test_telemetry_setup_mismatch_precedes_all_migrations_and_truncation(shadow_database):
    target, shadow = shadow_database
    engine = mismatched_engine(target, shadow)
    try:
        with pytest.raises(ValueError, match="differs"):
            prepare_telemetry_database(engine)
        assert_sentinel_intact(shadow)
    finally:
        engine.dispose()


def test_downgrade_007_checks_the_bound_server_before_ddl(shadow_database):
    target, shadow = shadow_database
    engine = mismatched_engine(target, shadow)
    spec = importlib.util.spec_from_file_location(
        "migration007", Path("migrations/versions/007_reliability.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="verified carerank_test"):
                migration.downgrade()
        assert_sentinel_intact(shadow)
    finally:
        engine.dispose()


def test_demo_mismatch_fails_before_reading_accounts_or_seeding(shadow_database, monkeypatch, tmp_path):
    target, shadow = shadow_database
    monkeypatch.setenv("APP_ENV", "development")
    engine = mismatched_engine(target, shadow, database="carerank_demo", username="carerank_demo_owner")
    try:
        with pytest.raises(ValueError, match="differs"):
            prepare(engine, tmp_path / "deliberately-missing-accounts.json")
        assert not event.contains(
            engine, "begin", __import__("app.demo", fromlist=["demo_connection"]).demo_connection
        )
        assert_sentinel_intact(shadow)
    finally:
        engine.dispose()


def test_connected_user_must_match_configuration(shadow_database):
    target, shadow = shadow_database
    engine = mismatched_engine(target, shadow, database=shadow.url.database, username="unapproved_owner")
    try:
        with engine.begin() as connection, pytest.raises(ValueError, match="differs"):
            postgres_connection(connection)
        assert_sentinel_intact(shadow)
    finally:
        engine.dispose()


def test_demo_revalidates_each_transaction_before_its_first_statement(shadow_database, monkeypatch):
    # Exercise the event lifecycle with the real disposable DB and a test-only
    # expected identity. The production guard still requires carerank_demo_owner.
    target, shadow = shadow_database
    import app.demo as demo

    calls = []
    monkeypatch.setattr(demo, "demo_configuration", lambda engine: None)

    def validate(connection):
        calls.append(1)
        postgres_connection(connection)
        if len(calls) >= 4:
            raise ValueError("Simulated later connection identity mismatch")

    monkeypatch.setattr(demo, "demo_connection", validate)
    with guarded_demo(shadow):
        with shadow.begin() as connection:
            connection.execute(text("SELECT 1"))
        with pytest.raises(ValueError, match="later connection"):
            with shadow.begin() as connection:
                connection.execute(text("DELETE FROM guard_sentinel"))
    assert_sentinel_intact(shadow)

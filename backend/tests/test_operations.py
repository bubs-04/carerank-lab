"""Real PostgreSQL scheduling, leases, recovery and authenticated control boundaries.

Schema resets and truncation are restricted to the reserved carerank_test database.
Fixtures never retrieve live CMS data; existing ingestion/monitoring code is exercised.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import os
import signal
import subprocess
import sys
import time
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.main import app
from app.db import get_engine
from app.auth.models import LoginLimit
from app.auth.security import now
from app.auth.service import create_user
from app.ingestion.models import IngestionRun, Snapshot
from app.monitoring.models import Alert, AuditEvent, Evaluation
from app.operations.models import Pipeline, Execution, Attempt, JobEvent
from app.operations import service

ORIGIN = "http://testserver"
PASSWORD = "Operations-test-only secret password!42"
CONFIG = {
    "name": "Deterministic registry pipeline",
    "source": "fixture_a",
    "max_rows": 5,
    "enabled": False,
    "interval_seconds": 60,
    "max_attempts": 3,
    "backoff_seconds": 1,
    "timeout_seconds": 120,
}


@pytest.fixture(scope="module")
def ops_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL carerank_test")
    target = make_url(url)
    if target.get_backend_name() != "postgresql" or target.database != "carerank_test":
        pytest.fail("Pipeline integration tests require PostgreSQL database carerank_test")
    keys = (
        "DATABASE_URL",
        "APP_ENV",
        "AUTH_COOKIE_SECURE",
        "AUTH_ALLOWED_ORIGINS",
        "AUTH_TRUSTED_PROXIES",
        "DQ_ENABLED",
    )
    original = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        DATABASE_URL=url,
        APP_ENV="development",
        AUTH_COOKIE_SECURE="false",
        AUTH_ALLOWED_ORIGINS=ORIGIN,
        AUTH_TRUSTED_PROXIES="",
        DQ_ENABLED="true",
    )
    get_engine.cache_clear()
    app.dependency_overrides.clear()
    command.upgrade(Config("alembic.ini"), "head")
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    get_engine.cache_clear()
    app.dependency_overrides.clear()
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def clean_jobs(ops_engine):
    # The module fixture has verified the exact disposable PostgreSQL database.
    with ops_engine.begin() as db:
        assert db.scalar(text("SELECT current_database()")) == "carerank_test"
        db.execute(text("TRUNCATE pipeline_definitions CASCADE"))
        db.execute(delete(LoginLimit))


def pipeline(engine, **overrides):
    with Session(engine) as db, db.begin():
        row = service.create_pipeline(db, {**CONFIG, **overrides})
        db.flush()
        return row.id


def enqueue(engine, pipeline_id, key=None):
    with Session(engine) as db, db.begin():
        row = service.enqueue(
            db, db.get(Pipeline, pipeline_id, with_for_update=True), key or uuid.uuid4().hex
        )
        db.flush()
        return row.id


def release_retry(engine, execution_id):
    with Session(engine) as db, db.begin():
        db.get(Execution, execution_id).available_at = now() - timedelta(seconds=1)


def expire_lease(engine, execution_id):
    with Session(engine) as db, db.begin():
        db.get(Execution, execution_id).lease_expires_at = now() - timedelta(seconds=1)


def execution_state(engine, execution_id):
    with Session(engine) as db:
        row = db.get(Execution, execution_id)
        return row.status, row.attempt_count, row.revision


@pytest.fixture
def accounts(ops_engine):
    suffix = uuid.uuid4().hex[:10]
    with Session(ops_engine) as db, db.begin():
        return {
            role: {"id": user.id, "username": user.username}
            for role in ("administrator", "analyst", "viewer")
            for user in [create_user(db, f"ops-{role}-{suffix}", f"Operations {role}", role, PASSWORD)]
        }


def login(account):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": account["username"], "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def test_concurrent_workers_claim_once_and_serialize_each_pipeline(ops_engine):
    pipeline_id = pipeline(ops_engine)
    first = enqueue(ops_engine, pipeline_id)
    second = enqueue(ops_engine, pipeline_id)
    barrier = Barrier(6)

    def compete(number):
        barrier.wait(timeout=10)
        return service.claim(ops_engine, f"concurrent-{number}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = [claim for claim in pool.map(compete, range(6)) if claim is not None]
    assert len(claims) == 1
    assert claims[0].execution_id in (first, second)
    with Session(ops_engine) as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
        assert (
            db.scalar(select(func.count()).select_from(Execution).where(Execution.status == "running")) == 1
        )
    service.execute_claim(ops_engine, claims[0])
    next_claim = service.claim(ops_engine, "next-worker")
    assert next_claim is not None and next_claim.execution_id != claims[0].execution_id
    service.execute_claim(ops_engine, next_claim)
    assert execution_state(ops_engine, first)[0] == execution_state(ops_engine, second)[0] == "succeeded"


def test_independent_pipelines_can_run_concurrently(ops_engine):
    ids = {enqueue(ops_engine, pipeline(ops_engine, name=f"Pipeline {i}")) for i in range(2)}
    barrier = Barrier(2)

    def compete(number):
        barrier.wait(timeout=10)
        return service.claim(ops_engine, f"parallel-{number}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(compete, range(2)))
    assert {claim.execution_id for claim in claims if claim} == ids
    assert len({claim.attempt_id for claim in claims}) == 2


def test_duplicate_manual_trigger_and_scheduling_are_idempotent(ops_engine):
    pipeline_id = pipeline(ops_engine, enabled=True)
    key = uuid.uuid4().hex
    first = enqueue(ops_engine, pipeline_id, key)
    assert enqueue(ops_engine, pipeline_id, key) == first
    with Session(ops_engine) as db, db.begin():
        db.get(Pipeline, pipeline_id).next_run_at = now() - timedelta(minutes=10)
    barrier = Barrier(4)

    def tick(_):
        barrier.wait(timeout=10)
        return service.schedule_due(ops_engine)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(tick, range(4)))
    with Session(ops_engine) as db:
        runs = list(db.scalars(select(Execution).where(Execution.pipeline_id == pipeline_id)))
        assert len(runs) == 2
        assert sum(row.trigger == "scheduled" for row in runs) == 1
        assert db.get(Pipeline, pipeline_id).next_run_at > now()
    assert service.schedule_due(ops_engine) == 0


def test_repeated_successful_executions_reuse_published_snapshot(ops_engine):
    pipeline_id = pipeline(ops_engine)
    ids = [enqueue(ops_engine, pipeline_id) for _ in range(2)]
    for number in range(2):
        service.execute_claim(ops_engine, service.claim(ops_engine, f"same-content-{number}"))
    with Session(ops_engine) as db:
        runs = [
            db.get(IngestionRun, db.get(Execution, execution_id).published_run_id) for execution_id in ids
        ]
        assert len({run.id for run in runs}) == 2
        assert len({run.snapshot_id for run in runs}) == 1
        assert runs[1].status == "no_change"
        assert all(db.get(Execution, execution_id).status == "succeeded" for execution_id in ids)
        assert all(
            db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.run_id == run.id)) == 12
            for run in runs
        )


def test_transient_failure_retries_with_backoff_and_retains_failure_evidence(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine, source="fixture_retry", backoff_seconds=60))
    first = service.claim(ops_engine, "failing-worker")
    service.execute_claim(ops_engine, first)
    with Session(ops_engine) as db:
        execution = db.get(Execution, execution_id)
        assert execution.status == "retry_wait" and execution.attempt_count == 1
        assert execution.available_at > now()
        attempt = db.get(Attempt, first.attempt_id)
        assert attempt.status == "failed" and attempt.error_code
        failed_run = db.get(IngestionRun, attempt.ingestion_run_id)
        assert failed_run.status == "failed" and failed_run.snapshot_id is None
        assert db.scalar(select(func.count()).select_from(Alert).where(Alert.run_id == failed_run.id)) >= 1
        failed_run_id = failed_run.id
    assert service.claim(ops_engine, "too-early") is None
    release_retry(ops_engine, execution_id)
    second = service.claim(ops_engine, "recovering-worker")
    assert second.number == 2 and second.attempt_id != first.attempt_id
    service.execute_claim(ops_engine, second)
    with Session(ops_engine) as db:
        execution = db.get(Execution, execution_id)
        assert execution.status == "succeeded" and execution.published_run_id
        assert db.get(IngestionRun, failed_run_id).status == "failed"
        assert db.get(Attempt, first.attempt_id).status == "failed"
        assert db.get(Attempt, second.attempt_id).status == "succeeded"
        assert (
            db.scalar(select(func.count()).select_from(Attempt).where(Attempt.execution_id == execution_id))
            == 2
        )
        assert (
            db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.execution_id == execution_id))
            >= 4
        )


def test_expired_worker_is_fenced_and_recovery_claim_is_distinct(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    old = service.claim(ops_engine, "orphaned-worker")
    expire_lease(ops_engine, execution_id)
    assert not service.heartbeat(ops_engine, old)
    assert service.recover_expired(ops_engine) == 1
    release_retry(ops_engine, execution_id)
    current = service.claim(ops_engine, "replacement-worker")
    assert current.attempt_id != old.attempt_id and current.number == 2
    # A late old process must not publish or finish the replacement's execution.
    service.execute_claim(ops_engine, old)
    assert execution_state(ops_engine, execution_id)[0] == "running"
    service.execute_claim(ops_engine, current)
    with Session(ops_engine) as db:
        assert db.get(Attempt, old.attempt_id).status == "interrupted"
        assert db.get(Attempt, current.attempt_id).status == "succeeded"
        assert db.get(Execution, execution_id).status == "succeeded"


def test_heartbeat_renews_only_current_unexpired_claim(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    current = service.claim(ops_engine, "heartbeat-worker", lease_seconds=10)
    with Session(ops_engine) as db:
        before = db.get(Execution, execution_id).lease_expires_at
    assert service.heartbeat(ops_engine, current, lease_seconds=30)
    with Session(ops_engine) as db:
        row = db.get(Execution, execution_id)
        assert row.heartbeat_at and row.lease_expires_at > before
    expire_lease(ops_engine, execution_id)
    assert not service.heartbeat(ops_engine, current, lease_seconds=30)


def test_exhausted_timeout_is_explicit_and_cannot_publish_late(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine, max_attempts=1))
    current = service.claim(ops_engine, "timed-out-worker")
    with Session(ops_engine) as db, db.begin():
        db.get(Execution, execution_id).deadline_at = now() - timedelta(seconds=1)
    assert service.recover_expired(ops_engine) == 1
    service.execute_claim(ops_engine, current)
    with Session(ops_engine) as db:
        assert db.get(Execution, execution_id).status == "timed_out"
        assert db.get(Execution, execution_id).published_run_id is None
        assert db.get(Attempt, current.attempt_id).status == "timed_out"
    assert service.claim(ops_engine, "cannot-retry") is None


def test_authenticated_cancellation_fences_a_running_worker(ops_engine, accounts):
    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    current = service.claim(ops_engine, "cancelled-worker")
    analyst, headers = login(accounts["analyst"])
    detail = analyst.get(f"/api/operations/executions/{execution_id}").json()
    response = analyst.post(
        f"/api/operations/executions/{execution_id}/cancel",
        headers=headers,
        json={"expected_revision": detail["revision"], "reason": "Stop this disposable test execution"},
    )
    assert response.status_code == 200, response.text
    service.execute_claim(ops_engine, current)
    with Session(ops_engine) as db:
        execution = db.get(Execution, execution_id)
        assert execution.status == "cancelled" and execution.published_run_id is None
        assert db.get(Attempt, current.attempt_id).status == "cancelled"
        cancelled = db.scalar(
            select(JobEvent).where(JobEvent.execution_id == execution_id, JobEvent.action == "cancelled")
        )
        assert cancelled.actor_user_id == accounts["analyst"]["id"]


def test_roles_csrf_and_trigger_idempotency_are_enforced_by_backend(ops_engine, accounts):
    pipeline_id = pipeline(ops_engine)
    execution_id = enqueue(ops_engine, pipeline_id)
    with TestClient(app) as anonymous:
        for path in (
            "/api/operations/pipelines",
            "/api/operations/executions",
            f"/api/operations/executions/{execution_id}",
        ):
            assert anonymous.get(path, headers={"X-Role": "administrator"}).status_code == 401
    viewer, viewer_headers = login(accounts["viewer"])
    analyst, analyst_headers = login(accounts["analyst"])
    assert viewer.get("/api/operations/pipelines").status_code == 200
    for client, headers in ((viewer, viewer_headers), (analyst, analyst_headers)):
        assert client.post("/api/operations/pipelines", headers=headers, json=CONFIG).status_code == 403
        assert (
            client.patch(
                f"/api/operations/pipelines/{pipeline_id}",
                headers=headers,
                json={"expected_revision": 1, "enabled": True},
            ).status_code
            == 403
        )
    assert (
        viewer.post(
            f"/api/operations/pipelines/{pipeline_id}/trigger",
            headers=viewer_headers,
            json={"idempotency_key": uuid.uuid4().hex},
        ).status_code
        == 403
    )
    assert (
        viewer.post(
            f"/api/operations/executions/{execution_id}/cancel",
            headers=viewer_headers,
            json={"expected_revision": 1, "reason": "Unauthorized"},
        ).status_code
        == 403
    )
    key = uuid.uuid4().hex
    url = f"/api/operations/pipelines/{pipeline_id}/trigger"
    for headers in ({}, {"Origin": ORIGIN}, {**analyst_headers, "Origin": "https://evil.invalid"}):
        assert analyst.post(url, headers=headers, json={"idempotency_key": key}).status_code == 403
    first = analyst.post(url, headers=analyst_headers, json={"idempotency_key": key})
    second = analyst.post(url, headers=analyst_headers, json={"idempotency_key": key})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_administrator_configuration_is_validated_and_revision_checked(ops_engine, accounts):
    admin, headers = login(accounts["administrator"])
    created = admin.post("/api/operations/pipelines", headers=headers, json=CONFIG)
    assert created.status_code in (200, 201), created.text
    pipeline_id = created.json()["id"]
    first = admin.patch(
        f"/api/operations/pipelines/{pipeline_id}",
        headers=headers,
        json={"expected_revision": 1, "enabled": True},
    )
    assert first.status_code == 200 and first.json()["revision"] == 2
    stale = admin.patch(
        f"/api/operations/pipelines/{pipeline_id}",
        headers=headers,
        json={"expected_revision": 1, "name": "Stale overwrite"},
    )
    assert stale.status_code == 409
    for invalid in (
        {"source": "../../private.csv"},
        {"max_rows": 5001},
        {"interval_seconds": 0},
        {"max_attempts": 0},
    ):
        assert (
            admin.post("/api/operations/pipelines", headers=headers, json={**CONFIG, **invalid}).status_code
            == 422
        )
    assert admin.get("/api/operations/pipelines").json()["items"][0]["enabled"] is True


def test_pipeline_events_are_append_only(ops_engine):
    enqueue(ops_engine, pipeline(ops_engine))
    with Session(ops_engine) as db:
        assert db.scalar(select(func.count()).select_from(JobEvent)) > 0
    for statement in ("UPDATE pipeline_events SET action='tampered'", "DELETE FROM pipeline_events"):
        with pytest.raises(DBAPIError), ops_engine.begin() as db:
            db.execute(text(statement))


def test_exponential_backoff_exhaustion_keeps_every_attempt(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine, backoff_seconds=7, max_attempts=3))
    for number in range(1, 4):
        current = service.claim(ops_engine, f"failed-worker-{number}")
        assert current.number == number
        assert service.finish_claim(ops_engine, current, "worker_error")
        with Session(ops_engine) as db:
            row, attempt = db.get(Execution, execution_id), db.get(Attempt, current.attempt_id)
            assert attempt.status == "failed" and attempt.error_code == "worker_error"
            if number < 3:
                assert row.status == "retry_wait"
                assert (row.available_at - attempt.finished_at).total_seconds() == 7 * 2 ** (number - 1)
            else:
                assert row.status == "failed" and row.finished_at
        if number < 3:
            assert service.claim(ops_engine, "before-backoff") is None
            release_retry(ops_engine, execution_id)
    assert service.claim(ops_engine, "after-exhaustion") is None
    with Session(ops_engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Attempt).where(Attempt.execution_id == execution_id))
            == 3
        )


def test_published_checkpoint_recovers_without_reingestion_or_duplicate_alerts(ops_engine, monkeypatch):
    from app.ingestion import service as ingestion

    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    first = service.claim(ops_engine, "lost-after-publication")
    # Preserve the exact durable state of a process lost after publication/evaluation
    # and before committing the queue completion record.
    with monkeypatch.context() as patch:
        patch.setattr(service, "finish_claim", lambda *args, **kwargs: False)
        service.execute_claim(ops_engine, first)
    with Session(ops_engine) as db:
        execution = db.get(Execution, execution_id)
        assert execution.status == "running" and execution.published_run_id
        published = execution.published_run_id
        before = {
            model: db.scalar(select(func.count()).select_from(model))
            for model in (IngestionRun, Snapshot, Evaluation, Alert, AuditEvent)
        }
    expire_lease(ops_engine, execution_id)
    assert service.recover_expired(ops_engine) == 1
    release_retry(ops_engine, execution_id)
    replacement = service.claim(ops_engine, "reconcile-published")
    assert replacement.published_run_id == published

    def forbidden_ingestion(*args, **kwargs):
        pytest.fail("A published execution must reconcile monitoring without ingesting again")

    monkeypatch.setattr(ingestion, "ingest", forbidden_ingestion)
    service.execute_claim(ops_engine, replacement)
    with Session(ops_engine) as db:
        assert db.get(Execution, execution_id).status == "succeeded"
        assert db.get(Execution, execution_id).published_run_id == published
        assert db.get(Attempt, replacement.attempt_id).ingestion_run_id == published
        assert before == {model: db.scalar(select(func.count()).select_from(model)) for model in before}


def test_manual_retry_preserves_cancelled_execution_and_rejects_stale_control(ops_engine, accounts):
    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    analyst, headers = login(accounts["analyst"])
    cancelled = analyst.post(
        f"/api/operations/executions/{execution_id}/cancel",
        headers=headers,
        json={"expected_revision": 1, "reason": "Cancel before delivery"},
    )
    assert cancelled.status_code == 200, cancelled.text
    key = str(uuid.uuid4())
    url = f"/api/operations/executions/{execution_id}/retry"
    assert (
        analyst.post(url, headers=headers, json={"expected_revision": 1, "idempotency_key": key}).status_code
        == 409
    )
    body = {"expected_revision": cancelled.json()["revision"], "idempotency_key": key}
    retried = analyst.post(url, headers=headers, json=body)
    assert retried.status_code == 200, retried.text
    assert retried.json()["id"] != execution_id
    assert analyst.post(url, headers=headers, json=body).json()["id"] == retried.json()["id"]
    service.execute_claim(ops_engine, service.claim(ops_engine, "manual-recovery"))
    with Session(ops_engine) as db:
        assert db.get(Execution, execution_id).status == "cancelled"
        assert db.get(Execution, retried.json()["id"]).status == "succeeded"


@pytest.mark.parametrize("baseline", ["005", "006"])
def test_migration_to_007_preserves_every_existing_table(ops_engine, accounts, baseline):
    login(accounts["administrator"])
    command.downgrade(Config("alembic.ini"), baseline)
    if baseline == "006":
        execution_id = enqueue(ops_engine, pipeline(ops_engine))
        service.execute_claim(ops_engine, service.claim(ops_engine, "migration-preservation"))
        assert execution_state(ops_engine, execution_id)[0] == "succeeded"
    with ops_engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO providers (id,name,specialty,location) VALUES (:id,'Synthetic preservation sentinel','Cardiology','Boston')"
            ),
            {"id": 800000 + int(baseline)},
        )
    with ops_engine.connect() as db:
        tables = [name for name in inspect(db).get_table_names() if name != "alembic_version"]
        columns = {table: [column["name"] for column in inspect(db).get_columns(table)] for table in tables}
        before = {
            table: sorted(
                repr(tuple(row))
                for row in db.execute(
                    text("SELECT " + ",".join(f'"{column}"' for column in names) + f' FROM "{table}"')
                )
            )
            for table, names in columns.items()
        }
    command.upgrade(Config("alembic.ini"), "head")
    with ops_engine.connect() as db:
        for table, names in columns.items():
            assert before[table] == sorted(
                repr(tuple(row))
                for row in db.execute(
                    text("SELECT " + ",".join(f'"{column}"' for column in names) + f' FROM "{table}"')
                )
            )
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "007"
        assert {
            "pipeline_definitions",
            "pipeline_executions",
            "pipeline_attempts",
            "pipeline_events",
            "pipeline_workers",
        }.issubset(inspect(db).get_table_names())


def test_terminated_worker_leaves_recoverable_attempt(ops_engine):
    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    process = subprocess.Popen(
        [sys.executable, "-m", "app.operations", "worker", "--once", "--lease-seconds", "3"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 20
        while execution_state(ops_engine, execution_id)[0] != "running":
            assert process.poll() is None, "Worker exited before claiming its execution"
            assert time.monotonic() < deadline, "Worker never claimed queued work"
            time.sleep(0.01)
        # Kill the real supervisor and its child group, not a fake database worker.
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        assert execution_state(ops_engine, execution_id)[0] == "running"
        expire_lease(ops_engine, execution_id)
        assert service.recover_expired(ops_engine) == 1
        release_retry(ops_engine, execution_id)
        replacement = service.claim(ops_engine, "surviving-worker")
        service.execute_claim(ops_engine, replacement)
        with Session(ops_engine) as db:
            attempts = list(
                db.scalars(
                    select(Attempt).where(Attempt.execution_id == execution_id).order_by(Attempt.number)
                )
            )
            assert [a.status for a in attempts] == ["interrupted", "succeeded"]
            assert db.get(Execution, execution_id).status == "succeeded"
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_cancellation_during_fetch_blocks_publication_and_reconciles_audit(ops_engine, monkeypatch):
    from app.ingestion import connector

    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    token = service.claim(ops_engine, "cancel-during-fetch")
    original = connector.fixture_batch

    def cancel_in_fetch(*args, **kwargs):
        with Session(ops_engine) as db, db.begin():
            row = db.get(Execution, execution_id)
            service.cancel_execution(db, row.id, row.revision, None, "Deterministic cancellation")
        return original(*args, **kwargs)

    monkeypatch.setattr(connector, "fixture_batch", cancel_in_fetch)
    service.execute_claim(ops_engine, token)
    service.reconcile_monitoring(ops_engine)
    with Session(ops_engine) as db:
        row, attempt = db.get(Execution, execution_id), db.get(Attempt, token.attempt_id)
        run = db.get(IngestionRun, attempt.ingestion_run_id)
        assert row.status == "cancelled" and row.published_run_id is None
        assert run.status == "interrupted" and run.snapshot_id is None
        assert (
            db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.run_id == run.id)) == 12
        )


def test_restricted_worker_executes_recovery_without_identity_or_owner_privileges(ops_engine):
    import secrets
    import psycopg
    from psycopg import sql
    from app.runtime_role import provision

    owner = make_url(os.environ["TEST_DATABASE_URL"])
    role = "carerank_worker_boundary_" + uuid.uuid4().hex[:10]
    worker = owner.set(username=role, password=secrets.token_hex(24))
    # Reprovisioning an old API role must remove even its column-level ACLs.
    provision(owner.render_as_string(hide_password=False), worker.render_as_string(hide_password=False))
    provision(
        owner.render_as_string(hide_password=False), worker.render_as_string(hide_password=False), worker=True
    )
    worker_engine = create_engine(worker)
    try:
        execution_id = enqueue(ops_engine, pipeline(ops_engine, source="fixture_retry"))
        first = service.claim(worker_engine, "restricted-worker")
        service.execute_claim(worker_engine, first)
        assert execution_state(ops_engine, execution_id)[0] == "retry_wait"
        release_retry(ops_engine, execution_id)
        service.execute_claim(worker_engine, service.claim(worker_engine, "restricted-recovery"))
        assert execution_state(ops_engine, execution_id)[0] == "succeeded"
        with psycopg.connect(worker.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
            for statement in [
                "SELECT * FROM auth_users",
                "UPDATE auth_users SET role='administrator' WHERE false",
                "UPDATE monitor_alerts SET status='resolved' WHERE false",
                "UPDATE providers SET name='forbidden' WHERE false",
                "UPDATE pipeline_definitions SET enabled=true WHERE false",
                "DELETE FROM pipeline_events WHERE false",
                "CREATE TABLE forbidden_worker_table(id int)",
            ]:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    db.execute(statement)
                db.rollback()
    finally:
        worker_engine.dispose()
        with psycopg.connect(owner.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_supervisor_tolerates_publication_heartbeat_lock_contention(ops_engine, monkeypatch):
    from app.operations import worker
    from sqlalchemy.exc import SQLAlchemyError

    execution_id = enqueue(ops_engine, pipeline(ops_engine))
    real_popen, real_heartbeat = subprocess.Popen, worker.heartbeat
    renewal_failures = []

    def slow_publication_child(args):
        # Use a real supervised process and real PostgreSQL locks. The existing
        # ingestion fault-injection seam holds publication across a heartbeat.
        return real_popen(
            [
                sys.executable,
                "-c",
                "import sys, time; "
                "from app.ingestion import service; "
                "from app.operations.__main__ import main; "
                "original = service.ingest; "
                "service.ingest = lambda *a, **k: original(*a, before_commit=lambda: time.sleep(7), **k); "
                "sys.argv = ['operations', 'execute', *sys.argv[1:]]; "
                "raise SystemExit(main())",
                *args[-2:],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def observed_heartbeat(*args, **kwargs):
        try:
            return real_heartbeat(*args, **kwargs)
        except SQLAlchemyError as exc:
            renewal_failures.append(exc)
            raise

    monkeypatch.setattr(worker.subprocess, "Popen", slow_publication_child)
    monkeypatch.setattr(worker, "heartbeat", observed_heartbeat)
    assert worker.work_once(ops_engine, "publication-contention", lease_seconds=12)
    assert renewal_failures, "The test must exercise a real heartbeat lock timeout"
    with Session(ops_engine) as db:
        execution = db.get(Execution, execution_id)
        attempt = db.scalar(select(Attempt).where(Attempt.execution_id == execution_id))
        assert execution.status == "succeeded" and execution.attempt_count == 1
        assert attempt.status == "succeeded" and attempt.error_code is None
        assert execution.published_run_id == attempt.ingestion_run_id


def test_claim_prioritizes_oldest_ready_work_across_pipeline_ids(ops_engine):
    lower_id, higher_id = sorted([pipeline(ops_engine), pipeline(ops_engine)])
    newer, older = enqueue(ops_engine, lower_id), enqueue(ops_engine, higher_id)
    with Session(ops_engine) as db, db.begin():
        db.get(Execution, newer).available_at = now() - timedelta(seconds=1)
        db.get(Execution, older).available_at = now() - timedelta(seconds=10)
    token = service.claim(ops_engine, "fair-worker")
    assert token.execution_id == older
    service.finish_claim(ops_engine, token)
    assert service.claim(ops_engine, "fair-worker").execution_id == newer


def test_restricted_api_retries_published_checkpoint_without_update_permission(
    ops_engine, accounts, monkeypatch
):
    import secrets
    import psycopg
    from psycopg import sql
    from app.auth.dependencies import get_auth_session
    from app.runtime_role import provision

    execution_id = enqueue(ops_engine, pipeline(ops_engine, max_attempts=1))
    token = service.claim(ops_engine, "publish-before-crash")
    with monkeypatch.context() as patch:
        patch.setattr(service, "finish_claim", lambda *args, **kwargs: None)
        service.execute_claim(ops_engine, token)
    expire_lease(ops_engine, execution_id)
    service.recover_expired(ops_engine)
    with Session(ops_engine) as db:
        old = db.get(Execution, execution_id)
        assert old.status == "failed" and old.published_run_id
        checkpoint, revision = old.published_run_id, old.revision
        before_runs = db.scalar(select(func.count()).select_from(IngestionRun))

    owner = make_url(os.environ["TEST_DATABASE_URL"])
    role = "carerank_api_retry_" + uuid.uuid4().hex[:10]
    runtime = owner.set(username=role, password=secrets.token_hex(24))
    provision(owner.render_as_string(hide_password=False), runtime.render_as_string(hide_password=False))
    runtime_engine = create_engine(runtime)

    def runtime_session():
        with Session(runtime_engine) as db:
            yield db

    app.dependency_overrides[get_auth_session] = runtime_session
    try:
        analyst, headers = login(accounts["analyst"])
        response = analyst.post(
            f"/api/operations/executions/{execution_id}/retry",
            headers=headers,
            json={"expected_revision": revision, "idempotency_key": str(uuid.uuid4())},
        )
        assert response.status_code == 200, response.text
        assert response.json()["published_run_id"] == checkpoint
        replacement = service.claim(ops_engine, "retry-monitoring-only")
        assert replacement.execution_id == response.json()["id"]
        service.execute_claim(ops_engine, replacement)
        with Session(ops_engine) as db:
            assert db.get(Execution, replacement.execution_id).status == "succeeded"
            assert db.scalar(select(func.count()).select_from(IngestionRun)) == before_runs
        with psycopg.connect(
            runtime.set(drivername="postgresql").render_as_string(hide_password=False)
        ) as db:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("UPDATE pipeline_executions SET published_run_id = NULL WHERE false")
            db.rollback()
    finally:
        app.dependency_overrides.pop(get_auth_session, None)
        runtime_engine.dispose()
        with psycopg.connect(owner.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_authenticated_history_pages_retain_total_and_order(ops_engine, accounts):
    pipeline_id = pipeline(ops_engine)
    ids = [enqueue(ops_engine, pipeline_id) for _ in range(3)]
    viewer, _ = login(accounts["viewer"])
    url = f"/api/operations/executions?pipeline_id={pipeline_id}&limit=2"
    first, second = viewer.get(url).json(), viewer.get(url + "&offset=2").json()
    assert first["total"] == second["total"] == 3
    assert [row["id"] for row in first["items"] + second["items"]] == list(reversed(ids))
    assert viewer.get(url + "&offset=-1").status_code == 422

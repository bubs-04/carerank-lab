"""Operational evidence, correlation privacy and fail-closed configuration."""

import io
import json
import logging
import os
import uuid
from datetime import timedelta
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.main import app
from app.db import get_engine
from app.auth.service import create_user
from app.observability import SafeJSONFormatter, request_id
from app.secrets import resolve_secret
from app.operations import service
from app.operations.models import Attempt, JobEvent
from app.operations.telemetry import WorkerPresence, pulse, worker_ready


@pytest.fixture(scope="module")
def telemetry_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL carerank_test")
    assert make_url(url).database == "carerank_test" and make_url(url).get_backend_name() == "postgresql"
    env = {
        "DATABASE_URL": url,
        "APP_ENV": "development",
        "AUTH_COOKIE_SECURE": "false",
        "AUTH_ALLOWED_ORIGINS": "http://testserver",
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    get_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("TRUNCATE pipeline_definitions CASCADE"))
        db.execute(text("DELETE FROM pipeline_workers"))
        db.execute(text("DELETE FROM auth_login_limits"))
    yield engine
    engine.dispose()
    get_engine.cache_clear()
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_logs_never_include_query_credentials_or_request_body():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJSONFormatter())
    logger = logging.getLogger("carerank.http")
    logger.addHandler(handler)
    try:
        with TestClient(app) as client:
            supplied = str(uuid.uuid4())
            result = client.get(
                "/api/live?password=never-log-this",
                headers={"X-Request-ID": supplied, "Authorization": "secret-header"},
            )
            assert result.status_code == 200 and result.headers["X-Request-ID"] == supplied
            assert request_id.get() is None
            other = client.get("/api/live", headers={"X-Request-ID": "injected-secret"})
            assert uuid.UUID(other.headers["X-Request-ID"])
            assert other.headers["X-Request-ID"] != supplied
        payload = stream.getvalue()
        assert all(secret not in payload for secret in ("never-log-this", "secret-header", "injected-secret"))
        records = [json.loads(line) for line in payload.splitlines()]
        assert records[0]["request_id"] == supplied and records[0]["route"] == "/api/live"
        assert records[0]["status_code"] == 200 and records[0]["duration_ms"] >= 0
    finally:
        logger.removeHandler(handler)


def test_mounted_secrets_conflicts_and_errors_are_sanitized(tmp_path, monkeypatch):
    path = tmp_path / "database-url"
    path.write_text("postgresql+psycopg://owner:privatepassword@localhost/carerank_test\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_FILE", str(path))
    assert resolve_secret("DATABASE_URL").endswith("/carerank_test")
    monkeypatch.setenv("DATABASE_URL", "secret-direct")
    get_engine.cache_clear()
    with pytest.raises(RuntimeError, match="Database configuration invalid") as error:
        get_engine()
    assert "privatepassword" not in str(error.value) and "secret-direct" not in str(error.value)
    get_engine.cache_clear()


def test_readiness_and_worker_staleness(telemetry_engine, monkeypatch):
    monkeypatch.setenv("WORKER_INSTANCE_ID", "verification-instance")
    with TestClient(app) as client:
        assert client.get("/api/live").json() == {"status": "ok"}
        assert client.get("/api/ready").status_code == 200
    assert not worker_ready(telemetry_engine)
    pulse(telemetry_engine, "verification-worker")
    assert worker_ready(telemetry_engine)
    with Session(telemetry_engine) as db, db.begin():
        row = db.get(WorkerPresence, "verification-worker")
        row.heartbeat_at = service.clock(db) - timedelta(seconds=31)
    assert not worker_ready(telemetry_engine)
    pulse(telemetry_engine, "verification-worker", "stopped")
    assert not worker_ready(telemetry_engine)


def test_metrics_are_authenticated_read_only_and_match_durable_history(telemetry_engine):
    password = "Metrics fixture password only 123!"
    with Session(telemetry_engine) as db, db.begin():
        viewer = create_user(db, "metrics-" + uuid.uuid4().hex[:8], "Metrics Viewer", "viewer", password)
        username = viewer.username
        config = {
            "name": "Metrics fixture",
            "source": "fixture_a",
            "max_rows": 5,
            "enabled": False,
            "interval_seconds": 60,
            "max_attempts": 2,
            "backoff_seconds": 1,
            "timeout_seconds": 30,
        }
        pipeline = service.create_pipeline(db, config)
        moment = service.clock(db)
        for status, duration, count in [("succeeded", 10, 2), ("failed", 30, 1), ("cancelled", None, 0)]:
            execution = service.enqueue(db, pipeline, uuid.uuid4().hex)
            execution.status = status
            execution.finished_at = moment
            execution.attempt_count = count
            execution.started_at = moment - timedelta(seconds=duration) if duration else None
            if count == 2:
                db.add(
                    Attempt(
                        id=str(uuid.uuid4()),
                        execution_id=execution.id,
                        number=2,
                        worker_id="fixture",
                        status="succeeded",
                        started_at=moment - timedelta(seconds=2),
                        finished_at=moment,
                        heartbeat_at=moment,
                        lease_expires_at=moment,
                    )
                )
    with TestClient(app) as client:
        assert client.get("/api/operations/reliability").status_code == 401
        login = client.post(
            "/api/auth/login",
            headers={"Origin": "http://testserver"},
            json={"username": username, "password": password},
        )
        assert login.status_code == 200
        before = client.get("/api/operations/reliability").json()
        assert before["summary"]["completed"] == 3 and before["summary"]["success_rate"] == 0.5
        assert (
            before["summary"]["p50_duration_seconds"] == 20
            and before["summary"]["p95_duration_seconds"] == 29
        )
        assert before["summary"]["retry_attempts"] == 1 and sum(x["retries"] for x in before["activity"]) == 1
        assert client.get("/api/operations/reliability?hours=169").status_code == 422
        assert client.post("/api/operations/reliability").status_code == 405
        assert client.get("/api/operations/reliability").json()["summary"] == before["summary"]


def test_request_id_is_linked_to_authenticated_job_decision(telemetry_engine):
    password = "Metrics admin password only 123!"
    with Session(telemetry_engine) as db, db.begin():
        user = create_user(
            db, "correlation-" + uuid.uuid4().hex[:8], "Metrics Admin", "administrator", password
        )
        username = user.username
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": "http://testserver"},
            json={"username": username, "password": password},
        )
        correlation = str(uuid.uuid4())
        result = client.post(
            "/api/operations/pipelines",
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": login.json()["csrf_token"],
                "X-Request-ID": correlation,
            },
            json={"name": "Correlated", "source": "fixture_a"},
        )
        assert result.status_code == 201
    with Session(telemetry_engine) as db:
        event = db.scalar(select(JobEvent).where(JobEvent.pipeline_id == result.json()["id"]))
        assert event.details["request_id"] == correlation and event.actor_user_id

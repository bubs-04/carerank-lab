"""Worker readiness follows completed checks, not a writable presence table."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.operations import telemetry, worker


@pytest.fixture
def supervisor(monkeypatch):
    engine = create_engine("sqlite://")
    telemetry.WorkerPresence.__table__.create(engine)
    moment = datetime.now(timezone.utc)
    monkeypatch.setenv("WORKER_INSTANCE_ID", "readiness-test")
    monkeypatch.setattr(telemetry, "clock", lambda db: moment)
    events = []

    def presence(engine, worker_id, state="idle", execution_id=None):
        events.append(("pulse", state))
        with Session(engine) as db, db.begin():
            db.merge(
                telemetry.WorkerPresence(
                    worker_id=worker_id,
                    instance_id=telemetry.instance_id(),
                    started_at=moment,
                    heartbeat_at=moment,
                    state=state,
                    execution_id=execution_id,
                )
            )

    monkeypatch.setattr(worker, "pulse", presence)
    for name in ("recover_expired", "reconcile_monitoring", "schedule_due", "claim"):
        monkeypatch.setattr(worker, name, Mock(side_effect=lambda *args, name=name: events.append(name)))
    yield engine, events
    engine.dispose()


def test_idle_requires_successful_maintenance_and_claim(supervisor):
    engine, events = supervisor
    assert not telemetry.worker_ready(engine)
    assert worker.work_once(engine, "test-worker") is False
    assert events == [
        "recover_expired",
        "reconcile_monitoring",
        "schedule_due",
        "claim",
        ("pulse", "idle"),
    ]
    assert telemetry.worker_ready(engine)


@pytest.mark.parametrize("stage", ["recover_expired", "reconcile_monitoring", "schedule_due", "claim"])
def test_failed_checks_clear_previous_healthy_presence(supervisor, monkeypatch, stage):
    engine, events = supervisor
    worker.work_once(engine, "test-worker")
    assert telemetry.worker_ready(engine)
    events.clear()
    failing_check = Mock(side_effect=SQLAlchemyError("synthetic-check-failure"))
    monkeypatch.setattr(worker, stage, failing_check)
    for _ in range(3):
        with pytest.raises(SQLAlchemyError, match="synthetic-check-failure"):
            worker.work_once(engine, "test-worker")
        assert not telemetry.worker_ready(engine)
    assert failing_check.call_count == 3
    assert [event for event in events if isinstance(event, tuple)] == [("pulse", "degraded")] * 3


def test_successful_tick_restores_degraded_worker(supervisor):
    engine, _ = supervisor
    worker.claim.side_effect = SQLAlchemyError("synthetic-claim-failure")
    with pytest.raises(SQLAlchemyError):
        worker.work_once(engine, "test-worker")
    assert not telemetry.worker_ready(engine)
    worker.claim.side_effect = None
    worker.claim.return_value = None
    assert worker.work_once(engine, "test-worker") is False
    assert telemetry.worker_ready(engine)


@pytest.mark.parametrize("failure", [SQLAlchemyError("claim-failed"), RuntimeError("tick-failed")])
def test_run_retries_failed_ticks_without_advertising_health(supervisor, monkeypatch, failure):
    engine, events = supervisor
    # The supervisor's PostgreSQL-only guard remains intact; all I/O is mocked here.
    monkeypatch.setattr(engine.dialect, "name", "postgresql")
    monkeypatch.setattr(worker.signal, "signal", Mock())
    worker.claim.side_effect = failure
    polls = []

    def poll(_seconds):
        assert events[-1] == ("pulse", "degraded")
        polls.append(True)
        if len(polls) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", poll)
    assert worker.run(engine) == 0
    assert len(polls) == 3 and worker.claim.call_count == 3
    assert events[-1] == ("pulse", "stopped")
    assert ("pulse", "idle") not in events


def test_failed_presence_write_preserves_original_tick_error(supervisor, monkeypatch):
    engine, _ = supervisor
    original = SQLAlchemyError("original-claim-failure")
    worker.claim.side_effect = original
    monkeypatch.setattr(worker, "pulse", Mock(side_effect=SQLAlchemyError("presence-unavailable")))
    with pytest.raises(SQLAlchemyError) as caught:
        worker.work_once(engine, "test-worker")
    assert caught.value is original


def test_lost_lease_is_not_renewed_as_healthy(supervisor, monkeypatch):
    engine, events = supervisor
    worker.claim.side_effect = None
    worker.claim.return_value = SimpleNamespace(execution_id="execution", attempt_id="attempt")
    child = Mock(returncode=None)
    child.poll.return_value = None
    monkeypatch.setattr(worker.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(worker, "terminate", Mock())
    monkeypatch.setattr(worker, "heartbeat", Mock(return_value=False))
    assert worker.work_once(engine, "test-worker") is True
    assert [event for event in events if isinstance(event, tuple)] == [
        ("pulse", "running"),
        ("pulse", "degraded"),
    ]
    assert not telemetry.worker_ready(engine)

"""PostgreSQL queue: at-least-once delivery, fenced publication and durable retries."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session
from ..auth.security import now, utc
from ..ingestion.models import IngestionRun, ValidationFinding
from .models import Pipeline, Execution, Attempt, JobEvent
from .schemas import PipelineConfig

ACTIVE = ("queued", "running", "retry_wait")
TERMINAL = ("succeeded", "failed", "cancelled", "timed_out")


class Conflict(ValueError):
    pass


class LostLease(Exception):
    pass


def clock(db):
    return db.scalar(select(func.clock_timestamp())) if db.bind.dialect.name == "postgresql" else now()


def event(db, pipeline_id, execution=None, action="queued", before=None, actor=None, details=None):
    db.add(
        JobEvent(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            execution_id=execution.id if execution else None,
            actor_user_id=actor,
            created_at=clock(db),
            action=action,
            from_status=before,
            to_status=execution.status if execution else None,
            details=details or {},
        )
    )


def policy(pipeline):
    return {key: getattr(pipeline, key) for key in PipelineConfig.model_fields}


def create_pipeline(db, config, actor_id=None):
    values = PipelineConfig(**config).model_dump()
    if db.scalar(select(func.count()).select_from(Pipeline)) >= 100:
        raise Conflict("Workspace pipeline limit reached")
    moment = clock(db)
    row = Pipeline(
        id=str(uuid.uuid4()),
        **values,
        revision=1,
        next_run_at=moment if values["enabled"] else None,
        created_at=moment,
        updated_at=moment,
    )
    db.add(row)
    db.flush()
    event(db, row.id, action="pipeline_created", actor=actor_id, details={"config": values})
    return row


def update_pipeline(db, pipeline_id, expected_revision, changes, actor_id=None):
    row = db.get(Pipeline, pipeline_id, with_for_update=True, populate_existing=True)
    if not row:
        raise LookupError("Pipeline not found")
    if row.revision != expected_revision:
        raise Conflict("Pipeline changed; reload its latest revision")
    if not changes or any(value is None for value in changes.values()):
        raise ValueError("Supply intentional non-null configuration changes")
    before = policy(row)
    values = PipelineConfig(**{**before, **changes}).model_dump()
    for key, value in values.items():
        setattr(row, key, value)
    moment = clock(db)
    if not row.enabled:
        row.next_run_at = None
    elif not before["enabled"] or before["interval_seconds"] != row.interval_seconds:
        row.next_run_at = moment
    row.revision += 1
    row.updated_at = moment
    event(
        db,
        row.id,
        action="pipeline_updated",
        actor=actor_id,
        details={"before": before, "after": values, "revision": row.revision},
    )
    return row


def enqueue(
    db, pipeline, key, trigger="manual", scheduled_for=None, actor_id=None, config=None, published_run_id=None
):
    # All callers hold the definition row lock (newly inserted definitions are also locked).
    existing = db.scalar(
        select(Execution).where(Execution.pipeline_id == pipeline.id, Execution.idempotency_key == key)
    )
    if existing:
        return existing
    if (
        db.scalar(
            select(func.count())
            .select_from(Execution)
            .where(Execution.pipeline_id == pipeline.id, Execution.status.in_(ACTIVE))
        )
        >= 20
    ):
        raise Conflict("Pipeline already has 20 active executions; wait or cancel queued work")
    values = config or policy(pipeline)
    moment = clock(db)
    row = Execution(
        id=str(uuid.uuid4()),
        pipeline_id=pipeline.id,
        idempotency_key=key,
        trigger=trigger,
        config=values,
        status="queued",
        revision=1,
        attempt_count=0,
        max_attempts=values["max_attempts"],
        scheduled_for=scheduled_for,
        created_at=moment,
        available_at=moment,
        published_run_id=published_run_id,
    )
    db.add(row)
    db.flush()
    event(
        db,
        pipeline.id,
        row,
        "queued",
        actor=actor_id,
        details={"trigger": trigger, "scheduled_for": scheduled_for.isoformat() if scheduled_for else None},
    )
    return row


def schedule_due(engine, limit=50):
    count = 0
    with Session(engine) as db, db.begin():
        moment = clock(db)
        rows = list(
            db.scalars(
                select(Pipeline)
                .where(Pipeline.enabled.is_(True), Pipeline.next_run_at <= moment)
                .order_by(Pipeline.next_run_at, Pipeline.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            due = utc(row.next_run_at)
            # Coalesce missed intervals: one durable occurrence, no unbounded catch-up storm.
            periods = int((moment - due).total_seconds() // row.interval_seconds) + 1
            try:
                enqueue(db, row, "scheduled:" + due.isoformat(), "scheduled", due)
                count += 1
            except Conflict:
                event(
                    db,
                    row.id,
                    action="schedule_deferred",
                    details={"reason": "active_execution_limit", "missed_intervals": periods},
                )
            row.next_run_at = due + timedelta(seconds=periods * row.interval_seconds)
    return count


@dataclass(frozen=True)
class Claim:
    execution_id: str
    attempt_id: str
    number: int
    config: dict
    published_run_id: str | None
    deadline_at: object


def claim(engine, worker_id, lease_seconds=30):
    if engine.dialect.name != "postgresql":
        raise ValueError("Durable workers require PostgreSQL")
    if not 3 <= lease_seconds <= 300 or not worker_id or len(worker_id) > 100:
        raise ValueError("Invalid worker lease configuration")
    with Session(engine) as db, db.begin():
        moment = clock(db)
        due = exists(
            select(Execution.id).where(
                Execution.pipeline_id == Pipeline.id,
                Execution.status.in_(("queued", "retry_wait")),
                Execution.available_at <= moment,
            )
        )
        running = exists(
            select(Execution.id).where(Execution.pipeline_id == Pipeline.id, Execution.status == "running")
        )
        oldest_due = (
            select(func.min(Execution.available_at))
            .where(
                Execution.pipeline_id == Pipeline.id,
                Execution.status.in_(("queued", "retry_wait")),
                Execution.available_at <= moment,
            )
            .correlate(Pipeline)
            .scalar_subquery()
        )
        pipeline = db.scalar(
            select(Pipeline)
            .where(due, ~running)
            .order_by(oldest_due, Pipeline.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if pipeline is None:
            return None
        row = db.scalar(
            select(Execution)
            .where(
                Execution.pipeline_id == pipeline.id,
                Execution.status.in_(("queued", "retry_wait")),
                Execution.available_at <= moment,
            )
            .order_by(Execution.available_at, Execution.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        before = row.status
        row.status, row.revision = "running", row.revision + 1
        row.attempt_count += 1
        row.started_at = row.started_at or moment
        row.heartbeat_at = moment
        row.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        row.deadline_at = moment + timedelta(seconds=row.config["timeout_seconds"])
        row.active_attempt_id = str(uuid.uuid4())
        attempt = Attempt(
            id=row.active_attempt_id,
            execution_id=row.id,
            number=row.attempt_count,
            worker_id=worker_id,
            status="running",
            started_at=moment,
            heartbeat_at=moment,
            lease_expires_at=row.lease_expires_at,
            ingestion_run_id=row.published_run_id,
        )
        db.add(attempt)
        event(
            db,
            row.pipeline_id,
            row,
            "claimed",
            before,
            details={
                "attempt": row.attempt_count,
                "worker_id": worker_id,
                "resume_publication": bool(row.published_run_id),
            },
        )
        return Claim(
            row.id, attempt.id, attempt.number, dict(row.config), row.published_run_id, row.deadline_at
        )


def owned(db, token, check_time=True):
    row = db.get(Execution, token.execution_id, with_for_update=True, populate_existing=True)
    if not row or row.status != "running" or row.active_attempt_id != token.attempt_id:
        raise LostLease()
    moment = clock(db)
    if check_time and (utc(row.lease_expires_at) <= moment or utc(row.deadline_at) <= moment):
        raise LostLease()
    return row


def heartbeat(engine, token, lease_seconds=30):
    with Session(engine) as db, db.begin():
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        try:
            row = owned(db, token)
        except LostLease:
            return False
        moment = clock(db)
        row.heartbeat_at, row.lease_expires_at = moment, moment + timedelta(seconds=lease_seconds)
        attempt = db.get(Attempt, token.attempt_id)
        attempt.heartbeat_at, attempt.lease_expires_at = moment, row.lease_expires_at
    return True


def repair_run(db, attempt, code):
    run = db.get(IngestionRun, attempt.ingestion_run_id) if attempt.ingestion_run_id else None
    if run and run.status == "running":
        moment = clock(db)
        run.status, run.error_code, run.finished_at = "interrupted", code, moment
        run.seconds = max(0, (moment - utc(run.started_at)).total_seconds())
        db.add(ValidationFinding(run_id=run.id, row_number=None, severity="error", code=code, field="batch"))


def failed(db, row, attempt, code, attempt_status="failed"):
    before, moment = row.status, clock(db)
    attempt.status, attempt.error_code, attempt.finished_at = attempt_status, code, moment
    repair_run(db, attempt, code)
    row.error_code, row.revision = code, row.revision + 1
    if row.attempt_count < row.max_attempts:
        row.status = "retry_wait"
        delay = min(3600, row.config["backoff_seconds"] * 2 ** (row.attempt_count - 1))
        row.available_at = moment + timedelta(seconds=delay)
    else:
        row.status = "timed_out" if attempt_status == "timed_out" else "failed"
        row.finished_at = moment
    row.lease_expires_at = None
    event(
        db,
        row.pipeline_id,
        row,
        "retry_scheduled" if row.status == "retry_wait" else row.status,
        before,
        details={
            "attempt": attempt.number,
            "error_code": code,
            "attempt_status": attempt_status,
            "published_run_id": row.published_run_id,
            "available_at": row.available_at.isoformat(),
        },
    )


def finish_claim(engine, token, error_code=None):
    with Session(engine) as db, db.begin():
        try:
            row = owned(db, token)
        except LostLease:
            return False
        attempt = db.get(Attempt, token.attempt_id)
        if error_code:
            failed(db, row, attempt, error_code)
        else:
            moment = clock(db)
            row.status, row.finished_at, row.revision = "succeeded", moment, row.revision + 1
            row.error_code, row.lease_expires_at = None, None
            attempt.status, attempt.finished_at = "succeeded", moment
            event(
                db,
                row.pipeline_id,
                row,
                "succeeded",
                "running",
                details={"attempt": attempt.number, "published_run_id": row.published_run_id},
            )
    return True


def recover_expired(engine, limit=50):
    with Session(engine) as db, db.begin():
        moment = clock(db)
        rows = list(
            db.scalars(
                select(Execution)
                .where(
                    Execution.status == "running",
                    or_(Execution.lease_expires_at <= moment, Execution.deadline_at <= moment),
                )
                .order_by(Execution.lease_expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            timeout = utc(row.deadline_at) <= moment
            failed(
                db,
                row,
                db.get(Attempt, row.active_attempt_id),
                "execution_timeout" if timeout else "worker_lease_expired",
                "timed_out" if timeout else "interrupted",
            )
        return len(rows)


def cancel_execution(db, execution_id, expected_revision, actor_id, reason):
    row = db.get(Execution, execution_id, with_for_update=True, populate_existing=True)
    if not row:
        raise LookupError("Execution not found")
    if row.revision != expected_revision:
        raise Conflict("Execution changed; reload its latest revision")
    if row.status not in ACTIVE:
        raise Conflict("Only active executions can be cancelled")
    if row.published_run_id:
        raise Conflict("Data is already published; allow monitoring reconciliation to finish")
    before, moment = row.status, clock(db)
    if row.status == "running":
        attempt = db.get(Attempt, row.active_attempt_id)
        attempt.status, attempt.finished_at, attempt.error_code = "cancelled", moment, "cancelled_by_user"
        # The API role cannot change registry evidence. The worker reconciles this
        # interrupted audit after cancellation has fenced out further publication.
    row.status, row.finished_at, row.error_code = "cancelled", moment, "cancelled_by_user"
    row.revision += 1
    row.lease_expires_at = None
    event(db, row.pipeline_id, row, "cancelled", before, actor_id, {"reason": reason})
    return row


def reconcile_monitoring(engine, limit=20):
    """Repair fenced interrupted audits and backfill monitoring without API write authority."""
    from ..monitoring.models import Evaluation
    from ..monitoring.service import evaluate_run
    from ..monitoring.config import MonitoringSettings

    with Session(engine) as db, db.begin():
        attempts = list(
            db.scalars(
                select(Attempt)
                .join(IngestionRun, IngestionRun.id == Attempt.ingestion_run_id)
                .where(Attempt.status != "running", IngestionRun.status == "running")
                .order_by(Attempt.started_at)
                .limit(limit)
                .with_for_update(of=IngestionRun, skip_locked=True)
            )
        )
        for attempt in attempts:
            repair_run(db, attempt, attempt.error_code or "worker_interrupted")
    if not MonitoringSettings().enabled:
        return 0
    with Session(engine) as db:
        ids = list(
            db.scalars(
                select(IngestionRun.id)
                .join(Attempt, Attempt.ingestion_run_id == IngestionRun.id)
                .where(
                    IngestionRun.status != "running",
                    ~exists(select(Evaluation.id).where(Evaluation.run_id == IngestionRun.id)),
                )
                .distinct()
                .limit(limit)
            )
        )
    count = 0
    for run_id in ids:
        try:
            evaluate_run(engine, run_id)
            count += 1
        except Exception:
            # Durable run/attempt links retain the pending work for the next tick.
            import logging

            logging.getLogger(__name__).warning("pipeline_monitoring_pending run_id=%s", run_id)
    return count


def execute_claim(engine, token):
    """Execute one fenced attempt; publication and its execution checkpoint commit together."""
    from pathlib import Path
    from ..auth.dependencies import settings
    from ..ingestion.connector import CMSConnector, fixture_batch
    from ..ingestion.config import IngestionSettings
    from ..ingestion.service import ingest
    from ..ingestion.validation import BatchError
    from ..monitoring.service import evaluate_run
    from ..monitoring.config import MonitoringSettings

    def guard(db):
        return owned(db, token)

    def started(db, run_id):
        db.get(Attempt, token.attempt_id).ingestion_run_id = run_id

    def published(db, run):
        row = owned(db, token)
        row.published_run_id = run.id

    try:
        with Session(engine) as db, db.begin():
            row = owned(db, token)
            run_id = row.published_run_id
        if not run_id:
            source = token.config["source"]
            maximum = token.config["max_rows"]
            if source == "cms":
                # The job policy supplies outer retries; avoid multiplying connector attempts.
                fetch = CMSConnector(IngestionSettings(max_rows=maximum, attempts=1)).fetch
            elif source in {"fixture_a", "fixture_b", "fixture_retry"}:
                if source == "fixture_retry" and settings().app_env != "development":
                    return finish_claim(engine, token, "demo_disabled")
                fixture = (
                    Path(__file__).resolve().parents[2]
                    / "tests"
                    / "fixtures"
                    / ("cms_registry_b.csv" if source == "fixture_b" else "cms_registry_a.csv")
                )

                def fetch():
                    if source == "fixture_retry" and token.number == 1:
                        raise BatchError("demo_transient_failure")
                    return fixture_batch(fixture, maximum)
            else:
                return finish_claim(engine, token, "invalid_source")
            run_id = ingest(
                engine,
                fetch,
                "cms" if source == "cms" else "fixture",
                maximum,
                run_id=token.attempt_id,
                transaction_guard=guard,
                on_started=started,
                on_published=published,
                evaluate=False,
            )
        # Reconcile previous interrupted attempts as well as this publication.
        if MonitoringSettings().enabled:
            with Session(engine) as db:
                previous = list(
                    db.scalars(
                        select(Attempt.ingestion_run_id).where(
                            Attempt.execution_id == token.execution_id, Attempt.ingestion_run_id.is_not(None)
                        )
                    )
                )
            for previous_id in set(previous + [run_id]):
                evaluate_run(engine, previous_id)
        with Session(engine) as db:
            run = db.get(IngestionRun, run_id)
            error = None if run.status in ("succeeded", "no_change") else run.error_code or "ingestion_failed"
        return finish_claim(engine, token, error)
    except LostLease:
        return False
    except Exception:
        # Never persist exception text, credentials, source payloads or connection strings.
        return finish_claim(engine, token, "worker_or_monitoring_error")

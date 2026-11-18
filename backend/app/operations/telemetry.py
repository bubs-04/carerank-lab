"""Durable worker presence and read-only aggregate reliability evidence."""

from datetime import datetime, timedelta
import os
import socket
from fastapi import APIRouter, Query
from sqlalchemy import DateTime, String, Index, select, func, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.dialects.postgresql import insert
from ..auth.dependencies import AuthDB, CurrentUser
from ..auth.security import utc
from ..ingestion.models import RegistryBase
from ..monitoring.models import Alert
from .models import Execution, Attempt
from .service import clock

STALE_SECONDS = 30
router = APIRouter(prefix="/api/operations", tags=["Reliability"])


class WorkerPresence(RegistryBase):
    __tablename__ = "pipeline_workers"
    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(100), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20))
    execution_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (Index("ix_pipeline_workers_heartbeat", "heartbeat_at"),)


def instance_id():
    value = os.environ.get("WORKER_INSTANCE_ID", socket.gethostname())
    if not value or len(value) > 100 or any(not (c.isalnum() or c in "._-") for c in value):
        raise ValueError("Invalid worker instance ID")
    return value


def pulse(engine, worker_id, state="idle", execution_id=None):
    with Session(engine) as db, db.begin():
        moment = clock(db)
        values = dict(
            worker_id=worker_id,
            instance_id=instance_id(),
            started_at=moment,
            heartbeat_at=moment,
            state=state,
            execution_id=execution_id,
        )
        db.execute(
            insert(WorkerPresence)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["worker_id"],
                set_={key: values[key] for key in ("heartbeat_at", "state", "execution_id")},
            )
        )
        # Presence is transient telemetry, not immutable execution/audit evidence.
        # Bound restart churn without removing job history.
        db.execute(
            text("DELETE FROM pipeline_workers WHERE heartbeat_at < clock_timestamp() - interval '7 days'")
        )


def worker_ready(engine):
    with Session(engine) as db:
        moment = clock(db)
        return bool(
            db.scalar(
                select(WorkerPresence.worker_id)
                .where(
                    WorkerPresence.instance_id == instance_id(),
                    WorkerPresence.state.in_(("idle", "running")),
                    WorkerPresence.heartbeat_at > moment - timedelta(seconds=STALE_SECONDS),
                )
                .limit(1)
            )
        )


@router.get("/reliability")
def reliability(identity: CurrentUser, db: AuthDB, hours: int = Query(24, ge=1, le=168)):
    moment = clock(db)
    since = moment - timedelta(hours=hours)
    # PG performs all aggregates: historical rows never materialize into the API.
    completed = Execution.finished_at.between(since, moment)
    aggregate = (
        db.execute(
            select(
                func.count().label("completed"),
                func.count().filter(Execution.status == "succeeded").label("succeeded"),
                func.count().filter(Execution.status.in_(("failed", "timed_out"))).label("failed"),
                func.count().filter(Execution.status == "cancelled").label("cancelled"),
                func.count().filter(Execution.attempt_count > 1).label("retried_executions"),
                func.percentile_cont(0.5)
                .within_group(func.extract("epoch", Execution.finished_at - Execution.started_at))
                .label("p50"),
                func.percentile_cont(0.95)
                .within_group(func.extract("epoch", Execution.finished_at - Execution.started_at))
                .label("p95"),
            ).where(completed)
        )
        .mappings()
        .one()
    )
    summary = {
        key: aggregate[key] for key in ("completed", "succeeded", "failed", "cancelled", "retried_executions")
    }
    denominator = summary["succeeded"] + summary["failed"]
    summary.update(
        success_rate=round(summary["succeeded"] / denominator, 4) if denominator else None,
        p50_duration_seconds=round(aggregate["p50"], 3) if aggregate["p50"] is not None else None,
        p95_duration_seconds=round(aggregate["p95"], 3) if aggregate["p95"] is not None else None,
        retry_attempts=db.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.number > 1, Attempt.started_at.between(since, moment))
        ),
    )
    queue = {key: 0 for key in ("queued", "running", "retry_wait")}
    queue.update(
        dict(
            db.execute(
                select(Execution.status, func.count())
                .where(Execution.status.in_(tuple(queue)))
                .group_by(Execution.status)
            ).all()
        )
    )
    queue["overdue_leases"] = db.scalar(
        select(func.count())
        .select_from(Execution)
        .where(
            Execution.status == "running",
            (Execution.lease_expires_at <= moment) | (Execution.deadline_at <= moment),
        )
    )
    oldest = db.scalar(
        select(func.min(Execution.available_at)).where(
            Execution.status.in_(("queued", "retry_wait")), Execution.available_at <= moment
        )
    )
    queue["oldest_ready_age_seconds"] = round((moment - utc(oldest)).total_seconds(), 3) if oldest else None
    states = list(db.scalars(select(WorkerPresence).order_by(WorkerPresence.heartbeat_at.desc()).limit(100)))
    workers = [
        {c.name: getattr(row, c.name) for c in WorkerPresence.__table__.columns}
        | {
            "age_seconds": max(0, round((moment - utc(row.heartbeat_at)).total_seconds(), 3)),
            "healthy": row.state in ("idle", "running")
            and utc(row.heartbeat_at) > moment - timedelta(seconds=STALE_SECONDS),
        }
        for row in states
    ]
    bucket = func.date_trunc("hour", Execution.finished_at)
    activity = [
        dict(row)
        for row in db.execute(
            select(
                bucket.label("hour"),
                func.count().label("completed"),
                func.count().filter(Execution.status == "succeeded").label("succeeded"),
                func.count().filter(Execution.status.in_(("failed", "timed_out"))).label("failed"),
            )
            .where(completed)
            .group_by(bucket)
            .order_by(bucket)
        ).mappings()
    ]
    by_hour = {row["hour"]: {**row, "retries": 0} for row in activity}
    retry_bucket = func.date_trunc("hour", Attempt.started_at)
    for hour, count in db.execute(
        select(retry_bucket, func.count())
        .where(Attempt.number > 1, Attempt.started_at.between(since, moment))
        .group_by(retry_bucket)
    ):
        by_hour.setdefault(hour, {"hour": hour, "completed": 0, "succeeded": 0, "failed": 0, "retries": 0})[
            "retries"
        ] = count
    activity = [by_hour[hour] for hour in sorted(by_hour)]
    return {
        "window": {"hours": hours, "from": since, "to": moment},
        "workers": workers,
        "summary": summary,
        "queue": queue,
        "activity": activity,
        "quality": {
            "open_alerts": db.scalar(
                select(func.count()).select_from(Alert).where(Alert.status != "resolved")
            ),
            "critical_open_alerts": db.scalar(
                select(func.count())
                .select_from(Alert)
                .where(Alert.status != "resolved", Alert.severity == "critical")
            ),
        },
        "limits": {"heartbeat_stale_seconds": STALE_SECONDS, "max_window_hours": 168},
        "generated_at": moment,
    }

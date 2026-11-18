"""Authenticated read views and role-checked durable commands; no work runs in HTTP."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select
from ..auth.dependencies import AuthDB, CurrentUser, Administrator, Analyst, settings
from ..auth.security import now, utc
from ..auth.service import security_lock, recheck_identity
from ..ingestion.models import IngestionRun
from .models import Pipeline, Execution, Attempt, JobEvent
from .schemas import PipelineConfig, PipelineUpdate, Trigger, Retry, Cancel
from . import service

router = APIRouter(prefix="/api/operations", tags=["Pipeline operations"])


def duration(start, finish):
    return max(0, ((utc(finish) if finish else now()) - utc(start)).total_seconds()) if start else None


def execution_view(db, row):
    result = {
        column.name: getattr(row, column.name)
        for column in Execution.__table__.columns
        if column.name not in {"idempotency_key", "active_attempt_id", "deadline_at"}
    }
    pipeline = db.get(Pipeline, row.pipeline_id)
    run = db.get(IngestionRun, row.published_run_id) if row.published_run_id else None
    result.update(
        pipeline_name=pipeline.name,
        snapshot_id=run.snapshot_id if run else None,
        duration_seconds=duration(row.started_at, row.finished_at),
    )
    return result


def pipeline_view(db, row):
    latest = db.scalar(
        select(Execution)
        .where(Execution.pipeline_id == row.id)
        .order_by(Execution.created_at.desc(), Execution.id.desc())
        .limit(1)
    )
    return {
        **{c.name: getattr(row, c.name) for c in Pipeline.__table__.columns},
        "latest_execution": execution_view(db, latest) if latest else None,
    }


def command(db, identity, roles, operation):
    security_lock(db)
    recheck_identity(db, identity, roles)
    try:
        result = operation()
        db.commit()
        return result
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except (ValueError, ValidationError):
        raise HTTPException(422, "Invalid pipeline policy or development-only source") from None


@router.get("/pipelines")
def pipelines(identity: CurrentUser, db: AuthDB):
    rows = list(db.scalars(select(Pipeline).order_by(Pipeline.created_at, Pipeline.id).limit(100)))
    return {
        "items": [pipeline_view(db, row) for row in rows],
        "demo_enabled": settings().app_env == "development",
    }


@router.post("/pipelines", status_code=201)
def create(body: PipelineConfig, identity: Administrator, db: AuthDB):
    return command(
        db,
        identity,
        {"administrator"},
        lambda: pipeline_view(db, service.create_pipeline(db, body.model_dump(), identity.user.id)),
    )


@router.patch("/pipelines/{pipeline_id}")
def configure(pipeline_id: str, body: PipelineUpdate, identity: Administrator, db: AuthDB):
    return command(
        db,
        identity,
        {"administrator"},
        lambda: pipeline_view(
            db,
            service.update_pipeline(
                db,
                pipeline_id,
                body.expected_revision,
                body.model_dump(exclude_unset=True, exclude={"expected_revision"}),
                identity.user.id,
            ),
        ),
    )


@router.post("/pipelines/{pipeline_id}/trigger")
def trigger(pipeline_id: str, body: Trigger, identity: Analyst, db: AuthDB):
    def operate():
        pipeline = db.get(Pipeline, pipeline_id, with_for_update=True, populate_existing=True)
        if not pipeline:
            raise LookupError("Pipeline not found")
        return execution_view(
            db,
            service.enqueue(db, pipeline, "manual:" + str(body.idempotency_key), actor_id=identity.user.id),
        )

    return command(db, identity, {"administrator", "analyst"}, operate)


@router.get("/executions")
def executions(
    identity: CurrentUser,
    db: AuthDB,
    pipeline_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if status is not None and status not in (*service.ACTIVE, *service.TERMINAL):
        raise HTTPException(422, "Unknown execution status")
    filters = [Execution.pipeline_id == pipeline_id] if pipeline_id else []
    metrics = {state: 0 for state in (*service.ACTIVE, *service.TERMINAL)}
    metrics.update(
        dict(
            db.execute(
                select(Execution.status, func.count()).where(*filters).group_by(Execution.status)
            ).all()
        )
    )
    if status:
        filters.append(Execution.status == status)
    rows = list(
        db.scalars(
            select(Execution)
            .where(*filters)
            .order_by(Execution.created_at.desc(), Execution.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return {
        "items": [execution_view(db, row) for row in rows],
        "total": db.scalar(select(func.count()).select_from(Execution).where(*filters)),
        "metrics": metrics,
    }


@router.get("/executions/{execution_id}")
def execution(execution_id: str, identity: CurrentUser, db: AuthDB):
    row = db.get(Execution, execution_id)
    if not row:
        raise HTTPException(404, "Execution not found")
    attempts = list(
        db.scalars(select(Attempt).where(Attempt.execution_id == row.id).order_by(Attempt.number))
    )
    events = list(
        db.scalars(
            select(JobEvent)
            .where(JobEvent.execution_id == row.id)
            .order_by(JobEvent.created_at, JobEvent.id)
            .limit(100)
        )
    )
    return {
        **execution_view(db, row),
        "attempts": [
            {
                **{c.name: getattr(a, c.name) for c in Attempt.__table__.columns},
                "duration_seconds": duration(a.started_at, a.finished_at),
            }
            for a in attempts
        ],
        "events": [{c.name: getattr(e, c.name) for c in JobEvent.__table__.columns} for e in events],
    }


@router.post("/executions/{execution_id}/cancel")
def cancel(execution_id: str, body: Cancel, identity: Analyst, db: AuthDB):
    return command(
        db,
        identity,
        {"administrator", "analyst"},
        lambda: execution_view(
            db,
            service.cancel_execution(db, execution_id, body.expected_revision, identity.user.id, body.reason),
        ),
    )


@router.post("/executions/{execution_id}/retry")
def retry(execution_id: str, body: Retry, identity: Analyst, db: AuthDB):
    def operate():
        old = db.get(Execution, execution_id, with_for_update=True, populate_existing=True)
        if not old:
            raise LookupError("Execution not found")
        pipeline = db.get(Pipeline, old.pipeline_id, with_for_update=True, populate_existing=True)
        key = "retry:" + old.id + ":" + str(body.idempotency_key)
        # A repeat response after a network interruption returns the same new execution.
        existing = db.scalar(
            select(Execution).where(Execution.pipeline_id == pipeline.id, Execution.idempotency_key == key)
        )
        if existing:
            return execution_view(db, existing)
        if old.revision != body.expected_revision or old.status not in {"failed", "timed_out", "cancelled"}:
            raise service.Conflict("Only the latest failed, timed-out or cancelled execution can be retried")
        # Copy the checkpoint in the INSERT: the API cannot alter publication
        # checkpoints after insertion; only the worker receives that authority.
        row = service.enqueue(
            db,
            pipeline,
            key,
            "retry",
            actor_id=identity.user.id,
            config=old.config,
            published_run_id=old.published_run_id,
        )
        service.event(
            db,
            pipeline.id,
            row,
            "retry_requested",
            actor=identity.user.id,
            details={"previous_execution_id": old.id},
        )
        return execution_view(db, row)

    return command(db, identity, {"administrator", "analyst"}, operate)

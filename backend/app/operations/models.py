"""Durable schedules, immutable execution policy, leased attempts and append-only events."""

from datetime import datetime
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..ingestion.models import RegistryBase


class Pipeline(RegistryBase):
    __tablename__ = "pipeline_definitions"
    __table_args__ = (
        CheckConstraint(
            "revision >= 1 AND interval_seconds >= 10 AND max_attempts BETWEEN 1 AND 5 AND backoff_seconds >= 1 AND timeout_seconds >= 5 AND max_rows BETWEEN 1 AND 5000",
            name="ck_pipeline_policy",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30))
    max_rows: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    backoff_seconds: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Execution(RegistryBase):
    __tablename__ = "pipeline_executions"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "idempotency_key", name="uq_pipeline_execution_key"),
        CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','failed','cancelled','timed_out')",
            name="ck_pipeline_execution_state",
        ),
        CheckConstraint(
            "revision >= 1 AND attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5",
            name="ck_pipeline_execution_attempts",
        ),
        Index("ix_pipeline_execution_due", "status", "available_at"),
        Index("ix_pipeline_execution_lease", "status", "lease_expires_at"),
        Index(
            "uq_pipeline_one_running",
            "pipeline_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipeline_definitions.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    trigger: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_attempt_id: Mapped[str | None] = mapped_column(String(36))
    published_run_id: Mapped[str | None] = mapped_column(ForeignKey("registry_runs.id"))
    error_code: Mapped[str | None] = mapped_column(String(100))


class Attempt(RegistryBase):
    __tablename__ = "pipeline_attempts"
    __table_args__ = (
        UniqueConstraint("execution_id", "number", name="uq_pipeline_attempt_number"),
        CheckConstraint(
            "status IN ('running','succeeded','failed','interrupted','cancelled','timed_out')",
            name="ck_pipeline_attempt_state",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("pipeline_executions.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    ingestion_run_id: Mapped[str | None] = mapped_column(ForeignKey("registry_runs.id"))


class JobEvent(RegistryBase):
    __tablename__ = "pipeline_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipeline_definitions.id"), index=True)
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_executions.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON)

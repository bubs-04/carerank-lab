"""Monitoring references registry history only. No cascading history deletion."""

from datetime import datetime
from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..ingestion.models import RegistryBase
from ..auth.models import User  # noqa: F401 — register FK target


class RuleVersion(RegistryBase):
    __tablename__ = "monitor_rules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20))
    threshold: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Evaluation(RegistryBase):
    __tablename__ = "monitor_evaluations"
    __table_args__ = (
        UniqueConstraint("run_id", "profile", "rule_version_id", name="uq_monitor_event_rule"),
        CheckConstraint("status IN ('passed','failed','not_evaluable')", name="ck_monitor_result"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("registry_runs.id"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("registry_snapshots.id"))
    baseline_run_id: Mapped[str | None] = mapped_column(ForeignKey("registry_runs.id"))
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("monitor_rules.id"), index=True)
    profile: Mapped[str] = mapped_column(String(64), index=True)
    observed: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(String(600))
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Alert(RegistryBase):
    __tablename__ = "monitor_alerts"
    __table_args__ = (
        UniqueConstraint("run_id", "rule_version_id", name="uq_monitor_alert_event_rule"),
        CheckConstraint(
            "status IN ('open','acknowledged','investigating','resolved')", name="ck_monitor_alert_state"
        ),
        CheckConstraint("revision >= 1", name="ck_monitor_alert_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("monitor_evaluations.id"), unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("registry_runs.id"), index=True)
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("monitor_rules.id"), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"))
    resolution: Mapped[str | None] = mapped_column(String(2000))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(RegistryBase):
    __tablename__ = "monitor_events"
    __table_args__ = (UniqueConstraint("alert_id", "revision", name="uq_monitor_audit_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("monitor_alerts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(100))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"))
    previous_assigned_to: Mapped[str | None] = mapped_column(String(100))
    previous_assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"))
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"))
    note: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

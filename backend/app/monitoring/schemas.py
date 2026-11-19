"""Typed monitoring reads and constrained analyst decisions; no patient records."""

from datetime import datetime
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from ..ingestion.schemas import RunView

ResultStatus = Literal["passed", "failed", "not_evaluable"]
AlertStatus = Literal["open", "acknowledged", "investigating", "resolved"]


class ORMView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RuleView(ORMView):
    id: str
    rule_id: str
    version: str
    description: str
    severity: str
    threshold: float
    unit: str


class EvaluationView(ORMView):
    id: str
    run_id: str
    snapshot_id: str | None
    baseline_run_id: str | None
    profile: str
    observed: float | None
    status: ResultStatus
    explanation: str
    evidence: dict
    created_at: datetime
    rule: RuleView


class AlertView(ORMView):
    id: str
    evaluation_id: str
    run_id: str
    rule_version_id: str
    severity: str
    status: AlertStatus
    assigned_to: str | None
    assigned_user_id: str | None
    resolution: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class EventView(ORMView):
    id: str
    alert_id: str
    revision: int
    actor: str
    actor_user_id: str | None
    previous_assigned_to: str | None
    previous_assigned_user_id: str | None
    action: str
    from_status: str | None
    to_status: str
    assigned_to: str | None
    assigned_user_id: str | None
    note: str
    created_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Summary(BaseModel):
    health: Literal["no_data", "disabled", "pending", "attention", "partial", "passed"]
    explanation: str
    profile: str
    expected_rules: int
    latest_run: RunView | None
    evaluations: dict[str, int]
    open_by_severity: dict[str, int]
    enabled: bool
    caveat: str


class AlertDetail(BaseModel):
    alert: AlertView
    evaluation: EvaluationView


class TrendPoint(BaseModel):
    run_id: str
    snapshot_id: str
    started_at: datetime
    ingestion_kind: Literal["fresh_cms_retrieval", "offline_archive_replay", "artificial_fixture"]
    provenance: dict
    archive_captured_at: datetime | None
    archive_replayed_at: datetime | None
    received: int
    valid: int
    rejected: int
    warnings: int


class Trend(BaseModel):
    reference_run_id: str | None
    scope: dict | None
    policy: str | None
    points: list[TrendPoint]
    caveat: str


class IncidentAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)
    status: AlertStatus | None = None
    assigned_to: str | None = Field(default=None, max_length=36)

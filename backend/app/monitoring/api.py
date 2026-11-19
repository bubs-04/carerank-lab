"""Authenticated monitoring reads and CSRF-protected analyst investigation."""

from collections import Counter
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select, func
from ..ingestion.api import DB, Page, Size, paged
from ..ingestion.models import DataSource, IngestionRun, Snapshot
from ..ingestion.schemas import RunView
from ..auth.dependencies import AuthDB, CurrentUser, Analyst
from . import schemas
from .config import MonitoringSettings
from .models import RuleVersion, Evaluation, Alert, AuditEvent
from .rules import CAVEAT, definitions, profile_id
from .service import SUCCESS, investigate_authenticated

router = APIRouter(prefix="/api/dataops/monitoring", tags=["Reliability monitoring and investigation"])
Mode = Literal["cms", "fixture"]


def current_profile():
    try:
        settings = MonitoringSettings()
    except ValidationError:
        raise HTTPException(
            503, "Monitoring configuration invalid. Check DQ_ environment variables."
        ) from None
    rules = definitions(settings)
    return settings, rules, profile_id(rules)


def evaluation_view(db, evaluation):
    return dict(
        **{name: getattr(evaluation, name) for name in schemas.EvaluationView.model_fields if name != "rule"},
        rule=db.get(RuleVersion, evaluation.rule_version_id),
    )


@router.get("/summary", response_model=schemas.Summary)
def summary(db: DB, mode: Mode = "cms"):
    settings, rules, profile = current_profile()
    latest = db.scalar(
        select(IngestionRun)
        .join(DataSource)
        .where(DataSource.mode == mode)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id)
        .limit(1)
    )
    counts = (
        dict(
            Counter(
                db.scalars(
                    select(Evaluation.status).where(
                        Evaluation.run_id == latest.id, Evaluation.profile == profile
                    )
                )
            )
        )
        if latest
        else {}
    )
    open_counts = dict(
        db.execute(
            select(Alert.severity, func.count())
            .join(IngestionRun, Alert.run_id == IngestionRun.id)
            .join(DataSource)
            .where(DataSource.mode == mode, Alert.status != "resolved")
            .group_by(Alert.severity)
        ).all()
    )
    if not latest:
        health, explanation = "no_data", "No ingestion attempts. Monitoring has no evidence yet."
    elif not settings.enabled:
        health, explanation = (
            "disabled",
            "Automatic monitoring is disabled by DQ_ENABLED. Historical alerts remain below.",
        )
    elif sum(counts.values()) != len(rules):
        health, explanation = (
            "pending",
            "Latest attempt is running or lacks the complete current rule profile. Run the evaluation CLI after completion.",
        )
    elif counts.get("failed", 0) or sum(open_counts.values()):
        health, explanation = (
            "attention",
            "A latest rule failed or earlier alerts still require investigation. Resolution does not rewrite a failed evaluation.",
        )
    elif counts.get("not_evaluable", 0):
        health, explanation = (
            "partial",
            "Available checks passed; some checks lack sufficient evidence or comparable history.",
        )
    else:
        health, explanation = (
            "passed",
            "All current rules passed for the latest attempt; no unresolved alerts. This is rule coverage, not a data certification.",
        )
    return dict(
        health=health,
        explanation=explanation,
        profile=profile,
        expected_rules=len(rules),
        latest_run=latest,
        evaluations=counts,
        open_by_severity=open_counts,
        enabled=settings.enabled,
        caveat=CAVEAT,
    )


@router.get("/rules", response_model=list[schemas.RuleView])
def rules():
    from dataclasses import asdict

    return [dict(id=r.id, **asdict(r)) for r in current_profile()[1]]


@router.get("/runs/{run_id}", response_model=RunView)
def run_detail(run_id: str, db: DB):
    run = db.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/evaluations", response_model=schemas.Page[schemas.EvaluationView])
def evaluations(
    db: DB,
    mode: Mode = "cms",
    run_id: str | None = Query(None, max_length=36),
    current_only: bool = True,
    page: Page = 1,
    page_size: Size = 20,
):
    query = (
        select(Evaluation)
        .join(IngestionRun, Evaluation.run_id == IngestionRun.id)
        .join(DataSource)
        .where(DataSource.mode == mode)
    )
    if run_id:
        query = query.where(Evaluation.run_id == run_id)
    if current_only:
        query = query.where(Evaluation.profile == current_profile()[2])
    result = paged(db, query.order_by(Evaluation.created_at.desc(), Evaluation.id), page, page_size)
    result["items"] = [evaluation_view(db, e) for e in result["items"]]
    return result


@router.get("/alerts", response_model=schemas.Page[schemas.AlertView])
def alerts(
    db: DB,
    identity: CurrentUser,
    mode: Mode = "cms",
    status: schemas.AlertStatus | None = None,
    severity: Literal["warning", "critical"] | None = None,
    assigned_to: Literal["me", "unassigned"] | None = None,
    page: Page = 1,
    page_size: Size = 20,
):
    query = (
        select(Alert)
        .join(IngestionRun, Alert.run_id == IngestionRun.id)
        .join(DataSource)
        .where(DataSource.mode == mode)
    )
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    if assigned_to == "me":
        query = query.where(Alert.assigned_user_id == identity.user.id)
    elif assigned_to == "unassigned":
        query = query.where(Alert.assigned_to.is_(None), Alert.assigned_user_id.is_(None))
    return paged(db, query.order_by(Alert.created_at.desc(), Alert.id), page, page_size)


@router.post("/alerts/{alert_id}/actions")
def incident_action(alert_id: str, body: schemas.IncidentAction, identity: Analyst, db: AuthDB):
    return investigate_authenticated(db, alert_id, identity, body)


@router.get("/alerts/{alert_id}", response_model=schemas.AlertDetail)
def alert_detail(alert_id: str, db: DB):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return dict(alert=alert, evaluation=evaluation_view(db, db.get(Evaluation, alert.evaluation_id)))


@router.get("/alerts/{alert_id}/events", response_model=schemas.Page[schemas.EventView])
def events(alert_id: str, db: DB, page: Page = 1, page_size: Size = 20):
    if not db.get(Alert, alert_id):
        raise HTTPException(404, "Alert not found")
    return paged(
        db,
        select(AuditEvent).where(AuditEvent.alert_id == alert_id).order_by(AuditEvent.revision.desc()),
        page,
        page_size,
    )


@router.get("/trends", response_model=schemas.Trend)
def trends(
    db: DB,
    mode: Mode = "cms",
    run_id: str | None = Query(None, max_length=36),
    limit: int = Query(20, ge=1, le=50),
):
    query = (
        select(IngestionRun).join(DataSource).where(DataSource.mode == mode, IngestionRun.status.in_(SUCCESS))
    )
    reference = (
        db.scalar(query.where(IngestionRun.id == run_id))
        if run_id
        else db.scalar(query.order_by(IngestionRun.started_at.desc(), IngestionRun.id).limit(1))
    )
    if run_id and not reference:
        raise HTTPException(422, "Choose a successful run from the selected source mode")
    snapshot = db.get(Snapshot, reference.snapshot_id) if reference else None
    points = []
    if snapshot:
        matching = query.join(Snapshot, IngestionRun.snapshot_id == Snapshot.id).where(
            Snapshot.source_id == snapshot.source_id,
            Snapshot.scope_hash == snapshot.scope_hash,
            Snapshot.policy == snapshot.policy,
            IngestionRun.started_at <= reference.started_at,
        )
        points = list(
            db.scalars(matching.order_by(IngestionRun.started_at.desc(), IngestionRun.id).limit(limit))
        )[::-1]
    return dict(
        reference_run_id=reference.id if reference else None,
        scope=snapshot.scope if snapshot else None,
        policy=snapshot.policy if snapshot else None,
        points=[trend_point(r, mode) for r in points],
        caveat=CAVEAT,
    )


def trend_point(run: IngestionRun, mode: Mode):
    # A no-change run may reuse a snapshot from a different retrieval method.
    # Provenance and replay time therefore belong to this attempt, not its snapshot.
    provenance = run.provenance
    replay = mode == "cms" and (
        provenance.get("archive_replay") is True
        or provenance.get("retrieval_method") == "verified_offline_cms_archive"
    )
    return dict(
        run_id=run.id,
        snapshot_id=run.snapshot_id,
        started_at=run.started_at,
        ingestion_kind="artificial_fixture"
        if mode == "fixture"
        else "offline_archive_replay"
        if replay
        else "fresh_cms_retrieval",
        provenance=provenance,
        archive_captured_at=provenance.get("archive_captured_at") if replay else None,
        archive_replayed_at=run.started_at if replay else None,
        **{key: getattr(run, key) for key in ("received", "valid", "rejected", "warnings")},
    )

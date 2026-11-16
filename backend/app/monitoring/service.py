"""Atomic evaluations and local-only investigation. Network I/O is never performed here."""

import logging
import uuid
from collections import Counter
from dataclasses import asdict
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from ..ingestion.models import IngestionRun, Snapshot, SourceRecord, ValidationFinding
from ..ingestion.service import now
from ..ingestion.compare import compare_versions
from ..ingestion.validation import canonical
from .config import MonitoringSettings
from .models import RuleVersion, Evaluation, Alert, AuditEvent
from .rules import CAVEAT, decide, definitions, profile_id

log = logging.getLogger(__name__)
TERMINAL = ("succeeded", "no_change", "failed", "interrupted")
SUCCESS = ("succeeded", "no_change")
TRANSITIONS = {
    "open": {"acknowledged", "investigating"},
    "acknowledged": {"investigating", "resolved"},
    "investigating": {"acknowledged", "resolved"},
    "resolved": {"open"},
}


def lock(db: Session):
    """Serialize short monitoring writes, including first rule registration and triage."""
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '10s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(721306)"))
    elif db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def baseline_for(db: Session, run: IngestionRun, snapshot: Snapshot):
    """Most recent compatible success finished before this attempt began; excludes overlaps."""
    return db.scalar(
        select(IngestionRun)
        .join(Snapshot, IngestionRun.snapshot_id == Snapshot.id)
        .where(
            IngestionRun.id != run.id,
            IngestionRun.status.in_(SUCCESS),
            IngestionRun.finished_at <= run.started_at,
            Snapshot.source_id == snapshot.source_id,
            Snapshot.scope_hash == snapshot.scope_hash,
            Snapshot.policy == snapshot.policy,
        )
        .order_by(IngestionRun.finished_at.desc(), IngestionRun.id)
        .limit(1)
    )


def measurements(db: Session, run: IngestionRun) -> tuple[dict, dict, str | None]:
    """Read SQL counts and bounded snapshot comparisons; do not reinterpret incomplete runs."""
    values = {"attempt_failure": float(run.status in ("failed", "interrupted"))}
    evidence = {
        "run_status": run.status,
        "received": run.received,
        "requested": run.requested,
        "error_code": run.error_code,
        "caveat": CAVEAT,
        "comparison_policy": "previous_completed_compatible_v1",
    }
    findings = list(
        db.execute(
            select(ValidationFinding.code, func.count())
            .where(ValidationFinding.run_id == run.id)
            .group_by(ValidationFinding.code)
        )
    )
    counts = dict(findings)
    contract = {
        k: v
        for k, v in counts.items()
        if k.startswith(("schema_", "metadata_")) or k in {"source_changed_during_download", "new_column"}
    }
    evidence["source_contract_findings"] = contract
    values["source_contract"] = float(sum(contract.values())) if contract or run.status in SUCCESS else None
    snapshot = db.get(Snapshot, run.snapshot_id) if run.snapshot_id else None
    complete = bool(
        run.status in SUCCESS
        and snapshot
        and run.finished_at
        and run.received == run.requested
        and (run.received, run.valid, run.rejected, run.warnings)
        == (snapshot.received, snapshot.valid, snapshot.rejected, snapshot.warnings)
        and snapshot.source_id == run.source_id
        and db.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.snapshot_id == snapshot.id)
        )
        == run.received
    )
    evidence["complete_snapshot"] = complete
    if not complete:
        evidence["unavailable_reason"] = (
            "No complete successful snapshot; partial counts are not zero errors."
        )
        return values, evidence, None
    evidence.update(
        snapshot_id=snapshot.id,
        scope=snapshot.scope,
        scope_hash=snapshot.scope_hash,
        validation_policy=snapshot.policy,
        source_id=snapshot.source_id,
        valid=run.valid,
        rejected=run.rejected,
        warnings=run.warnings,
    )
    values["rejected_rate"] = 100 * run.rejected / run.received
    for rule_id, code, field in [("duplicate_rate", "duplicate_identity", None)] + [
        (f"missing_{f}", "missing_optional", f) for f in ("pri_spec", "citytown", "state")
    ]:
        query = select(func.count(func.distinct(ValidationFinding.row_number))).where(
            ValidationFinding.run_id == run.id, ValidationFinding.code == code
        )
        if field:
            query = query.where(ValidationFinding.field == field)
        numerator = db.scalar(query)
        evidence[rule_id + "_rows"] = numerator
        values[rule_id] = 100 * numerator / run.received
    baseline = baseline_for(db, run, snapshot)
    if not baseline:
        evidence["baseline_reason"] = (
            "No previous completed run with the same source, scope and validation policy."
        )
        return values, evidence, None
    old = db.get(Snapshot, baseline.snapshot_id)
    evidence.update(
        baseline_run_id=baseline.id,
        baseline_snapshot_id=old.id,
        baseline_received=old.received,
        baseline_valid=old.valid,
        baseline_warnings=old.warnings,
    )
    values["warning_change"] = abs(100 * run.warnings / run.received - 100 * old.warnings / old.received)
    values["accepted_change"] = 100 * abs(run.valid - old.valid) / old.valid
    comparison = compare_versions(db, old.id, snapshot.id)
    # Union denominator is consistent for added, removed and changed; avoids percentages > 100.
    union = sum(comparison[k] for k in ("added", "removed", "changed", "unchanged"))
    evidence["comparison"] = {
        k: comparison[k]
        for k in (
            "added",
            "removed",
            "changed",
            "unchanged",
            "specialty_changes",
            "location_changes",
            "validation_delta",
        )
    }
    evidence["union_denominator"] = union
    for kind in ("added", "removed", "changed"):
        values[f"{kind}_rate"] = 100 * comparison[kind] / union if union else None
    return values, evidence, baseline.id


def evaluate_run(engine, run_id: str, settings: MonitoringSettings | None = None, before_commit=None) -> dict:
    """Persist a whole profile and new alerts/events atomically. Safe under concurrent reruns."""
    settings = settings or MonitoringSettings()
    rules = definitions(settings)
    profile = profile_id(rules)
    with Session(engine) as db, db.begin():
        lock(db)
        run = db.get(IngestionRun, run_id)
        if not run:
            raise LookupError("run_not_found")
        if run.status not in TERMINAL or run.finished_at is None:
            return dict(
                run_id=run_id, status="pending", reason="Attempt is not terminal; no zero-error inference."
            )
        existing = list(
            db.scalars(select(Evaluation).where(Evaluation.run_id == run_id, Evaluation.profile == profile))
        )
        if existing:
            if len(existing) != len(rules):
                raise ValueError("incomplete_evaluation_profile")
            return dict(
                run_id=run_id, profile=profile, reused=True, counts=dict(Counter(e.status for e in existing))
            )
        values, evidence, baseline_id = measurements(db, run)
        results = []
        for rule in rules:
            if not db.get(RuleVersion, rule.id):
                db.add(RuleVersion(id=rule.id, **asdict(rule), created_at=now()))
                db.flush()
            observed = values.get(rule.rule_id)
            reason = (
                evidence.get("unavailable_reason") or evidence.get("baseline_reason") or "Metric unavailable."
            )
            result = decide(rule, observed, evidence, reason if observed is None else "")
            evaluation = Evaluation(
                id=str(uuid.uuid4()),
                run_id=run.id,
                snapshot_id=run.snapshot_id,
                baseline_run_id=baseline_id,
                rule_version_id=rule.id,
                profile=profile,
                created_at=now(),
                **result,
            )
            db.add(evaluation)
            db.flush()
            results.append(evaluation)
            duplicate = db.scalar(
                select(Alert).where(Alert.run_id == run.id, Alert.rule_version_id == rule.id)
            )
            if result["status"] == "failed" and not duplicate:
                alert = Alert(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation.id,
                    run_id=run.id,
                    rule_version_id=rule.id,
                    severity=rule.severity,
                    status="open",
                    revision=1,
                    created_at=now(),
                    updated_at=now(),
                )
                db.add(alert)
                db.flush()
                db.add(
                    AuditEvent(
                        id=str(uuid.uuid4()),
                        alert_id=alert.id,
                        revision=1,
                        actor="system",
                        action="created",
                        from_status=None,
                        to_status="open",
                        note=evaluation.explanation,
                        created_at=now(),
                    )
                )
        if before_commit:
            before_commit()
        result = dict(
            run_id=run.id, profile=profile, reused=False, counts=dict(Counter(e.status for e in results))
        )
    log.info(canonical({"event": "monitoring_evaluated", **result}))
    return result


def evaluate_safely(engine, run_id: str):
    """Post-commit hook: monitoring failure never converts a published ingestion into failure."""
    try:
        settings = MonitoringSettings()
        if settings.enabled:
            evaluate_run(engine, run_id, settings)
    except Exception as exc:
        log.error(
            canonical({"event": "monitoring_pending", "run_id": run_id, "exception_type": type(exc).__name__})
        )


def investigate(
    engine,
    alert_id: str,
    *,
    actor: str,
    note: str,
    expected_revision: int,
    status: str | None = None,
    assignee: str | None = None,
    before_commit=None,
) -> dict:
    """Local operator assertion, not authenticated identity. Optimistic revision prevents lost decisions."""
    if not actor.strip() or len(actor) > 100 or not note.strip() or len(note) > 2000:
        raise ValueError("actor_and_note_required_within_limits")
    if assignee is not None and len(assignee) > 100:
        raise ValueError("assignee_too_long")
    with Session(engine) as db, db.begin():
        lock(db)
        alert = db.get(Alert, alert_id, with_for_update=True)
        if not alert:
            raise LookupError("alert_not_found")
        if alert.revision != expected_revision:
            raise ValueError("stale_revision_inspect_alert_again")
        previous = alert.status
        if status is not None and status not in TRANSITIONS[previous]:
            raise ValueError("invalid_alert_transition")
        if status:
            alert.status = status
            alert.resolution = note.strip() if status == "resolved" else None
        if assignee is not None:
            alert.assigned_to = assignee.strip() or None
        alert.revision += 1
        alert.updated_at = now()
        db.add(
            AuditEvent(
                id=str(uuid.uuid4()),
                alert_id=alert.id,
                revision=alert.revision,
                actor=actor.strip(),
                action="transition" if status else "note",
                from_status=previous,
                to_status=alert.status,
                assigned_to=alert.assigned_to,
                note=note.strip(),
                created_at=now(),
            )
        )
        db.flush()
        if before_commit:
            before_commit()
        return dict(alert_id=alert.id, status=alert.status, revision=alert.revision)

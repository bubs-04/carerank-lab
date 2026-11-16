"""Durable run audit plus atomic snapshot publication. CLI is the only write entrypoint."""

import logging
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session
from .config import BASE, DATASET, POLICY
from .models import DataSource, IngestionRun, Snapshot, SourceRecord, ValidationFinding, SnapshotChange
from .validation import BatchError, canonical, digest, validate
from .compare import compare_versions

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def registry_lock(db):
    """Serialize short registry commits across workers; never hold over network I/O."""
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '10s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(721305)"))


def ingest(engine, fetch, mode: str, requested: int, before_commit=None) -> str:
    """Create audit, fetch/validate off-transaction, atomically commit all rows or none."""
    from ..monitoring.service import evaluate_safely

    if mode not in {"cms", "fixture"} or not 1 <= requested <= 5000:
        raise ValueError("invalid_ingestion_configuration")
    run_id, source_id, started = str(uuid.uuid4()), f"{mode}-{DATASET}", time.monotonic()
    with Session(engine) as db, db.begin():
        registry_lock(db)
        if not db.get(DataSource, source_id):
            db.add(
                DataSource(
                    id=source_id,
                    dataset_id=DATASET,
                    mode=mode,
                    title="CMS Doctors and Clinicians"
                    if mode == "cms"
                    else "Deterministic fixture (not CMS retrieval)",
                    url=f"{BASE}/dataset/{DATASET}",
                )
            )
            db.flush()
        db.add(
            IngestionRun(
                id=run_id,
                source_id=source_id,
                started_at=now(),
                status="running",
                requested=requested,
                provenance={},
            )
        )
    log.info(canonical({"event": "ingestion_started", "run_id": run_id, "mode": mode}))
    batch, result = None, None
    try:
        batch = fetch()
        if (
            len(batch.rows) != requested
            or batch.scope.get("max_rows") != requested
            or batch.provenance.get("mode") != mode
        ):
            raise BatchError("incomplete_or_mismatched_batch", len(batch.rows))
        result = validate(batch.rows, batch.headers)
        if result.valid == 0:
            raise BatchError("no_valid_records", len(batch.rows))
        checksum = digest({"headers": sorted(batch.headers), "rows": batch.rows})
        scope_hash = digest(batch.scope)
        with Session(engine) as db, db.begin():
            registry_lock(db)
            run = db.get(IngestionRun, run_id)
            counts = dict(Counter(f["code"] for f in result.findings))
            existing = db.scalar(
                select(Snapshot).where(
                    Snapshot.source_id == source_id,
                    Snapshot.scope_hash == scope_hash,
                    Snapshot.checksum == checksum,
                    Snapshot.policy == POLICY,
                )
            )
            run.provenance = batch.provenance
            run.received, run.valid, run.rejected, run.warnings = (
                len(batch.rows),
                result.valid,
                result.rejected,
                result.warnings,
            )
            if existing:
                run.snapshot_id, run.status = existing.id, "no_change"
            else:
                previous = db.scalar(
                    select(Snapshot)
                    .join(IngestionRun, IngestionRun.snapshot_id == Snapshot.id)
                    .where(
                        IngestionRun.status.in_(["succeeded", "no_change"]),
                        Snapshot.source_id == source_id,
                        Snapshot.scope_hash == scope_hash,
                        Snapshot.policy == POLICY,
                    )
                    .order_by(IngestionRun.finished_at.desc(), IngestionRun.id)
                    .limit(1)
                )
                snapshot_id = str(uuid.uuid4())
                db.add(
                    Snapshot(
                        id=snapshot_id,
                        source_id=source_id,
                        created_at=now(),
                        checksum=checksum,
                        scope_hash=scope_hash,
                        scope=batch.scope,
                        provenance=batch.provenance,
                        policy=POLICY,
                        received=len(batch.rows),
                        valid=result.valid,
                        rejected=result.rejected,
                        warnings=result.warnings,
                        finding_counts=counts,
                    )
                )
                db.flush()
                db.execute(insert(SourceRecord), [dict(snapshot_id=snapshot_id, **r) for r in result.records])
                run.snapshot_id, run.status = snapshot_id, "succeeded"
                if previous:
                    db.add(
                        SnapshotChange(
                            old_id=previous.id,
                            new_id=snapshot_id,
                            created_at=now(),
                            summary=compare_versions(db, previous.id, snapshot_id),
                        )
                    )
            if result.findings:
                db.execute(insert(ValidationFinding), [dict(run_id=run_id, **f) for f in result.findings])
            run.finished_at, run.seconds = now(), time.monotonic() - started
            final_status = run.status
            if before_commit:
                before_commit()  # Fault injection seam; not exposed via HTTP or CLI.
    except BaseException as exc:
        status = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
        code = (
            exc.code
            if isinstance(exc, BatchError)
            else "interrupted"
            if status == "interrupted"
            else "internal_error"
        )
        with Session(engine) as db, db.begin():
            run = db.get(IngestionRun, run_id)
            run.status, run.error_code, run.finished_at, run.seconds = (
                status,
                code,
                now(),
                time.monotonic() - started,
            )
            run.provenance = (
                batch.provenance if batch else getattr(getattr(fetch, "__self__", None), "provenance", {})
            )
            run.received = len(batch.rows) if batch else getattr(exc, "received", None)
            if result:
                run.valid, run.rejected, run.warnings = result.valid, result.rejected, result.warnings
                if result.findings:
                    db.execute(insert(ValidationFinding), [dict(run_id=run_id, **f) for f in result.findings])
            db.add(
                ValidationFinding(run_id=run_id, row_number=None, severity="error", code=code, field="batch")
            )
        log.error(
            canonical(
                {
                    "event": "ingestion_finished",
                    "run_id": run_id,
                    "status": status,
                    "error_code": code,
                    "exception_type": type(exc).__name__,
                }
            )
        )
        evaluate_safely(engine, run_id)
        if status == "interrupted":
            raise
        return run_id
    log.info(canonical({"event": "ingestion_finished", "run_id": run_id, "status": final_status}))
    evaluate_safely(engine, run_id)
    return run_id

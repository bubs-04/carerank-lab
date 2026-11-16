"""Read-only DataOps endpoints. No ingestion trigger or user-supplied network URL."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_session
from .models import DataSource, IngestionRun, Snapshot, SourceRecord, ValidationFinding
from . import schemas
from .compare import compare_versions

router = APIRouter(prefix="/api/dataops", tags=["Public registry DataOps"])
DB = Annotated[Session, Depends(get_session)]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]


def paged(db, query, page, page_size):
    """Stable caller-provided ordering and bounded SQL pagination."""
    return dict(
        items=list(db.scalars(query.offset((page - 1) * page_size).limit(page_size))),
        total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery())),
        page=page,
        page_size=page_size,
    )


@router.get("/status", response_model=schemas.StatusView)
def status(db: DB, mode: Literal["cms", "fixture"] = "cms"):
    """Latest attempt and successful/no-change run; fixture history is explicitly separate."""
    sources = list(db.scalars(select(DataSource).where(DataSource.mode == mode)))
    ids = [s.id for s in sources]
    latest = (
        select(IngestionRun)
        .where(IngestionRun.source_id.in_(ids))
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id)
    )
    return dict(
        sources=sources,
        latest_attempt=db.scalar(latest.limit(1)),
        latest_success=db.scalar(latest.where(IngestionRun.status.in_(["succeeded", "no_change"])).limit(1)),
        snapshot_count=db.scalar(
            select(func.count()).select_from(Snapshot).where(Snapshot.source_id.in_(ids))
        ),
    )


@router.get("/versions", response_model=schemas.SnapshotPage)
def versions(db: DB, mode: Literal["cms", "fixture"] = "cms", page: Page = 1, page_size: Size = 20):
    """Published snapshots only: staging or failed transactions never appear here."""
    return paged(
        db,
        select(Snapshot)
        .join(DataSource)
        .where(DataSource.mode == mode)
        .order_by(Snapshot.created_at.desc(), Snapshot.id),
        page,
        page_size,
    )


@router.get("/runs", response_model=schemas.RunPage)
def runs(db: DB, mode: Literal["cms", "fixture"] = "cms", page: Page = 1, page_size: Size = 20):
    return paged(
        db,
        select(IngestionRun)
        .join(DataSource)
        .where(DataSource.mode == mode)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id),
        page,
        page_size,
    )


@router.get("/runs/{run_id}/findings", response_model=schemas.FindingPage)
def findings(run_id: str, db: DB, page: Page = 1, page_size: Size = 50):
    if not db.get(IngestionRun, run_id):
        raise HTTPException(404, "Run not found")
    return paged(
        db,
        select(ValidationFinding).where(ValidationFinding.run_id == run_id).order_by(ValidationFinding.id),
        page,
        page_size,
    )


@router.get("/versions/{snapshot_id}/records", response_model=schemas.RecordPage)
def records(snapshot_id: str, db: DB, page: Page = 1, page_size: Size = 50):
    if not db.get(Snapshot, snapshot_id):
        raise HTTPException(404, "Snapshot not found")
    return paged(
        db,
        select(SourceRecord).where(SourceRecord.snapshot_id == snapshot_id).order_by(SourceRecord.row_number),
        page,
        page_size,
    )


@router.get("/compare", response_model=schemas.ComparisonView)
def compare(
    db: DB, old_id: str = Query(min_length=1, max_length=36), new_id: str = Query(min_length=1, max_length=36)
):
    """Recompute any compatible successful pair without database writes."""
    try:
        return compare_versions(db, old_id, new_id)
    except LookupError as exc:
        raise HTTPException(404, "Snapshot not found") from exc
    except ValueError as exc:
        raise HTTPException(422, "Snapshots must share source, sampling scope and validation policy") from exc

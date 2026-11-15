import logging
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .db import get_session
from . import repository
from .schemas import Analytics, ProviderPage, ProviderView, RunView

app = FastAPI(
    title="CareRank Lab",
    version="1.0.0",
    description="Synthetic educational intelligence. Not clinical advice.",
)
DB = Annotated[Session, Depends(get_session)]


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    """Return a safe service error without exposing credentials or query internals."""
    logging.getLogger(__name__).error("database_error type=%s", type(error).__name__)
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable. Check connection and migrations."}
    )


@app.get("/api/health")
def health(db: DB) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/providers", response_model=ProviderPage)
def providers(
    db: DB,
    q: str = Query("", max_length=100),
    specialty: str | None = None,
    location: str | None = None,
    min_quality: float | None = Query(None, ge=0, le=100),
    max_cost: float | None = Query(None, gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: Literal["quality", "cost"] = "quality",
):
    return repository.search(db, q, specialty, location, min_quality, max_cost, page, page_size, sort)


@app.get("/api/compare", response_model=list[ProviderView])
def compare(db: DB, ids: Annotated[list[int], Query(min_length=2, max_length=3)]):
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Select distinct providers")
    rows = [repository.get_provider(db, i) for i in ids]
    if any(r is None for r in rows):
        raise HTTPException(404, "Provider not found")
    if len({r["specialty"] for r in rows}) != 1:
        raise HTTPException(422, "Compare providers within one specialty")
    return rows


@app.get("/api/providers/{provider_id}", response_model=ProviderView)
def detail(provider_id: int, db: DB):
    row = repository.get_provider(db, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found")
    return row


@app.get("/api/analytics", response_model=Analytics)
def analytics(db: DB):
    return repository.analytics(db)


@app.get("/api/pipeline", response_model=list[RunView])
def pipeline_status(db: DB):
    return repository.runs(db)

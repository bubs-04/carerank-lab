import logging
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .auth.api import router as auth_router
from .operations.api import router as operations_router
from .operations.telemetry import router as telemetry_router
from .auth.dependencies import require_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .db import get_session
from .ingestion.api import router as dataops_router
from .monitoring.api import router as monitoring_router
from . import repository, analytics as cohort_analytics
from .schemas import Analytics, ProviderPage, ProviderView, RunView, QualityCost, Evidence
from .observability import RequestLogMiddleware, configure_logging

configure_logging()

app = FastAPI(
    title="CareRank Lab",
    version="6.0.0",
    description="Synthetic educational intelligence. Not clinical advice.",
)
app.add_middleware(RequestLogMiddleware)
DB = Annotated[Session, Depends(get_session)]


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    """Return a safe service error without exposing credentials or query internals."""
    logging.getLogger(__name__).error(
        "database_error", extra={"event": "database_error", "error_type": type(error).__name__}
    )
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable. Check connection and migrations."}
    )


@app.get("/api/health")
def health(db: DB) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/live")
def live():
    return {"status": "ok"}


@app.get("/api/ready")
def ready(db: DB):
    if db.scalar(text("SELECT version_num FROM alembic_version")) != "007":
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ok"}


@app.get("/api/providers", dependencies=[Depends(require_user)], response_model=ProviderPage)
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


@app.get("/api/compare", dependencies=[Depends(require_user)], response_model=list[ProviderView])
def compare(db: DB, ids: Annotated[list[int], Query(min_length=2, max_length=3)]):
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Select distinct providers")
    rows = [repository.get_provider(db, i) for i in ids]
    if any(r is None for r in rows):
        raise HTTPException(404, "Provider not found")
    if len({r["specialty"] for r in rows}) != 1:
        raise HTTPException(422, "Compare providers within one specialty")
    return rows


@app.get("/api/providers/{provider_id}", dependencies=[Depends(require_user)], response_model=ProviderView)
def detail(provider_id: int, db: DB):
    row = repository.get_provider(db, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found")
    return row


@app.get("/api/analytics", dependencies=[Depends(require_user)], response_model=Analytics)
def analytics(db: DB):
    return repository.analytics(db)


@app.get("/api/pipeline", dependencies=[Depends(require_user)], response_model=list[RunView])
def pipeline_status(db: DB):
    return repository.runs(db)


@app.get("/api/analytics/quality-cost", dependencies=[Depends(require_user)], response_model=QualityCost)
def quality_cost(db: DB, specialty: str = Query("Cardiology", min_length=1, max_length=50)):
    """All scored providers in one specialty, raw mean costs and SQL cohort means.

    Highlight means strictly below mean cost AND above mean heuristic score.
    Unknown specialties return an empty cohort, not a cross-specialty fallback.
    """
    return cohort_analytics.quality_cost(db, specialty)


@app.get("/api/analytics/evidence", dependencies=[Depends(require_user)], response_model=Evidence)
def evidence(db: DB):
    """Disjoint eligibility counts and exact completeness bins across all providers.

    Insufficient outcomes takes precedence over low completeness. Zero encounters
    have undefined completeness. Missing score rows are reported as not processed.
    """
    return cohort_analytics.evidence(db)


app.include_router(auth_router)
app.include_router(operations_router)
app.include_router(telemetry_router)

app.include_router(dataops_router, dependencies=[Depends(require_user)])

app.include_router(monitoring_router, dependencies=[Depends(require_user)])


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    # FastAPI's default includes rejected inputs, which can contain passwords.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]
        },
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response

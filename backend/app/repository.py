from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import Provider, Score, PipelineRun, Encounter


def provider_query():
    """Join identity and materialized performance; no N+1 loading."""
    return select(Provider, Score).join(Score, Provider.id == Score.provider_id)


def serialize(provider, score) -> dict:
    """Map database records to the explicit public response shape."""
    return {
        "id": provider.id,
        "name": provider.name,
        "specialty": provider.specialty,
        "location": provider.location,
        "encounters": score.encounters,
        "observed": score.observed,
        "avg_cost": score.avg_cost,
        "quality": score.quality,
        "rank": score.rank,
        "components": score.components,
    }


def search(
    session: Session,
    q: str,
    specialty: str | None,
    location: str | None,
    min_quality: float | None,
    max_cost: float | None,
    page: int,
    page_size: int,
    sort: str,
) -> dict:
    """Bind filters, count matches, and apply stable ordering and bounded pagination."""
    query = provider_query()
    if q:
        query = query.where(Provider.name.icontains(q, autoescape=True))
    if specialty:
        query = query.where(Provider.specialty == specialty)
    if location:
        query = query.where(Provider.location == location)
    if min_quality is not None:
        query = query.where(Score.quality >= min_quality)
    if max_cost is not None:
        query = query.where(Score.avg_cost <= max_cost)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    order = Score.avg_cost.asc() if sort == "cost" else Score.quality.desc().nulls_last()
    rows = session.execute(
        query.order_by(order, Provider.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [serialize(p, s) for p, s in rows], "total": total, "page": page, "page_size": page_size}


def get_provider(session: Session, provider_id: int) -> dict | None:
    """Return a single profile, or None for a nonexistent identifier."""
    row = session.execute(provider_query().where(Provider.id == provider_id)).first()
    return serialize(*row) if row else None


def runs(session: Session) -> list:
    """Return the 20 newest execution audit rows."""
    return list(session.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(20)))


def analytics(session: Session) -> dict:
    """Aggregate dashboard facts, excluding null scores from the histogram and mean."""
    buckets = []
    for lo in range(0, 100, 20):
        upper = Score.quality <= 100 if lo == 80 else Score.quality < lo + 20
        n = session.scalar(select(func.count()).select_from(Score).where(Score.quality >= lo, upper))
        buckets.append({"name": f"{lo}–{lo + 20}", "count": n})
    return {
        "providers": session.scalar(select(func.count()).select_from(Provider)),
        "encounters": session.scalar(select(func.count()).select_from(Encounter)),
        "scored": session.scalar(select(func.count(Score.quality))),
        "mean_score": session.scalar(select(func.avg(Score.quality))),
        "specialties": [
            {"name": s, "count": n}
            for s, n in session.execute(
                select(Provider.specialty, func.count())
                .group_by(Provider.specialty)
                .order_by(Provider.specialty)
            )
        ],
        "distribution": buckets,
        "locations": list(session.scalars(select(Provider.location).distinct().order_by(Provider.location))),
        "latest_run": session.scalar(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)),
        "last_success": session.scalar(
            select(PipelineRun)
            .where(PipelineRun.status == "success")
            .order_by(PipelineRun.finished_at.desc())
            .limit(1)
        ),
    }

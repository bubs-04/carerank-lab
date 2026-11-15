"""Read-only cohort analytics over materialized scores; no encounter rows leave SQL."""

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session
from .models import Provider, Score


def quality_cost(db: Session, specialty: str) -> dict:
    filters = (Provider.specialty == specialty, Score.quality.is_not(None))
    # Snapshot isolation in get_session keeps summary and points consistent.
    mean_cost, mean_score = db.execute(
        select(func.avg(Score.avg_cost), func.avg(Score.quality))
        .select_from(Provider)
        .join(Score)
        .where(*filters)
    ).one()
    rows = db.execute(
        select(Provider.id, Provider.name, Score.avg_cost, Score.quality)
        .join(Score)
        .where(*filters)
        .order_by(Provider.id)
    ).all()
    return dict(
        specialty=specialty,
        count=len(rows),
        mean_cost=mean_cost,
        mean_score=mean_score,
        items=[
            dict(id=i, name=n, avg_cost=c, quality=q, highlighted=c < mean_cost and q > mean_score)
            for i, n, c, q in rows
        ],
    )


def evidence(db: Session) -> dict:
    # Ordered CASE assigns exactly one reason, even when both thresholds fail.
    reason = case(
        (Score.provider_id.is_(None), "not_processed"),
        (Score.quality.is_not(None), "eligible"),
        (Score.observed < 30, "insufficient_outcomes"),
        (Score.observed * 5 < Score.encounters * 4, "low_completeness"),
        else_="not_processed",
    )
    categories = ("eligible", "insufficient_outcomes", "low_completeness", "not_processed")
    counts = db.execute(
        select(Provider.specialty, reason.label("reason"), func.count())
        .outerjoin(Score)
        .group_by(Provider.specialty, reason)
        .order_by(Provider.specialty)
    ).all()
    grouped = {}
    for specialty, category, count in counts:
        grouped.setdefault(specialty, dict(specialty=specialty, **dict.fromkeys(categories, 0)))
        grouped[specialty][category] = count
    # Zero encounters have undefined completeness, separate from 0% observed outcomes.
    completeness = cast(Score.observed, Float) / func.nullif(Score.encounters, 0)
    bucket = case(
        (Score.provider_id.is_(None), "Not processed"),
        (Score.encounters == 0, "No encounters"),
        (completeness < 0.2, "0–<20%"),
        (completeness < 0.4, "20–<40%"),
        (completeness < 0.6, "40–<60%"),
        (completeness < 0.8, "60–<80%"),
        else_="80–100%",
    )
    bins = dict(
        db.execute(select(bucket, func.count()).select_from(Provider).outerjoin(Score).group_by(bucket)).all()
    )
    labels = ("0–<20%", "20–<40%", "40–<60%", "60–<80%", "80–100%", "No encounters", "Not processed")
    return dict(
        total=sum(n for _, _, n in counts),
        specialties=list(grouped.values()),
        completeness=[dict(name=k, count=bins.get(k, 0)) for k in labels],
    )

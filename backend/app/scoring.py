"""Transparent demo heuristic. Scores have no validated clinical interpretation."""

import math
from collections import defaultdict


def clamp(value: float) -> float:
    """Bound a component to the display range [0,100]."""
    return max(0, min(100, value))


def score_provider(total: int, observed: int, residual: float, cost_ratio: float) -> dict:
    """Shrink toward neutral using observed/(observed+50); suppress weak evidence."""
    if (
        total < 0
        or not 0 <= observed <= total
        or cost_ratio <= 0
        or not all(math.isfinite(x) for x in (residual, cost_ratio))
    ):
        raise ValueError("Invalid aggregate")
    completeness = observed / total if total else 0
    weight = observed / (observed + 50)
    outcome = clamp(50 + 250 * residual * weight)
    cost = clamp(50 + 50 * (1 - cost_ratio) * weight)
    reliability = 100 * completeness * weight
    volume = 100 * min(total / 200, 1)
    eligible = observed >= 30 and completeness >= 0.8
    quality = (
        round(0.60 * outcome + 0.25 * cost + 0.10 * reliability + 0.05 * volume, 2) if eligible else None
    )
    return {
        "quality": quality,
        "outcome": round(outcome, 2),
        "cost": round(cost, 2),
        "reliability": round(reliability, 2),
        "volume": round(volume, 2),
        "completeness": round(completeness, 4),
        "shrinkage": round(weight, 4),
        "residual": round(residual, 6),
        "cost_ratio": round(cost_ratio, 4),
        "status": "Scored" if eligible else "Insufficient data",
        "version": "demo-v1",
    }


def rank_specialties(rows: list[dict]) -> list[dict]:
    """Mutate rows with competition ranks by specialty; tied rounded scores share rank."""
    groups = defaultdict(list)
    for row in rows:
        row["rank"] = None
        if row["quality"] is not None:
            groups[row["specialty"]].append(row)
    for group in groups.values():
        group.sort(key=lambda r: (-r["quality"], r["provider_id"]))
        previous = None
        rank = 0
        for position, row in enumerate(group, 1):
            if row["quality"] != previous:
                rank = position
            row["rank"] = rank
            previous = row["quality"]
    return rows

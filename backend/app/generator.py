"""Reproducible fictional records; no real providers, patients or clinical measures."""

import random

SPECIALTIES = ("Cardiology", "Dermatology", "Orthopedics", "Primary Care", "Neurology")
LOCATIONS = ("New York, NY", "Austin, TX", "Boston, MA", "Denver, CO", "Seattle, WA")
BASE_COST = dict(zip(SPECIALTIES, (420, 160, 350, 120, 300)))
PROCEDURES = {"Consultation": 1.0, "Diagnostic": 1.7, "Follow-up": 0.65}


def expected_success(risk: float) -> float:
    """Known synthetic expectation, deliberately not a fitted clinical model."""
    return 0.95 - 0.30 * risk


def generate(providers: int = 1000, encounters: int = 100000, seed: int = 42):
    """Return provider/event dictionaries with stable IDs and a private random generator."""
    if not 1 <= providers <= 10000 or not 0 <= encounters <= 1000000:
        raise ValueError("Dataset size outside demo limits")
    rng = random.Random(seed)
    ps = [
        {
            "id": i,
            "name": f"Demo Provider {i:04d}",
            "specialty": SPECIALTIES[(i - 1) % 5],
            "location": rng.choice(LOCATIONS),
        }
        for i in range(1, providers + 1)
    ]
    skill = {p["id"]: rng.uniform(-0.10, 0.04) for p in ps}
    efficiency = {p["id"]: rng.uniform(0.75, 1.3) for p in ps}
    chosen = rng.choices(ps, weights=[0.1 if p["id"] % 17 == 0 else 1 for p in ps], k=encounters)
    rows = []
    for i, p in enumerate(chosen, 1):
        risk = round(rng.betavariate(2, 3), 4)
        procedure = rng.choice(tuple(PROCEDURES))
        cost = (
            BASE_COST[p["specialty"]]
            * PROCEDURES[procedure]
            * (1 + risk)
            * efficiency[p["id"]]
            * rng.uniform(0.85, 1.15)
        )
        outcome = int(rng.random() < expected_success(risk) + skill[p["id"]])
        rows.append(
            {
                "id": i,
                "provider_id": p["id"],
                "procedure": procedure,
                "risk": risk,
                "cost": round(cost, 2),
                "outcome": None if rng.random() < 0.025 else outcome,
            }
        )
    return ps, rows

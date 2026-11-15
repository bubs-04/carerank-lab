import pytest
from app.scoring import score_provider, rank_specialties
from app.generator import generate
from app.validation import validate


def test_reproducible():
    assert generate(20, 100, 9) == generate(20, 100, 9)
    assert generate(20, 100, 9) != generate(20, 100, 10)


@pytest.mark.parametrize("total,observed", [(0, 0), (29, 29), (100, 79)])
def test_insufficient(total, observed):
    assert score_provider(total, observed, 0, 1)["quality"] is None


def test_thresholds_and_direction():
    assert score_provider(30, 30, 0, 1)["quality"] is not None
    assert score_provider(100, 80, 0, 1)["quality"] is not None
    base = score_provider(100, 100, 0, 1)
    assert score_provider(100, 100, 0.1, 1)["quality"] > base["quality"]
    assert score_provider(100, 100, 0, 0.8)["quality"] > base["quality"]
    assert score_provider(30, 30, 0.1, 1)["outcome"] < score_provider(300, 300, 0.1, 1)["outcome"]


def test_worked_example():
    result = score_provider(100, 100, 0.04, 0.8)
    assert result["quality"] == 57.33
    assert result["outcome"] == 56.67


@pytest.mark.parametrize("args", [(-1, 0, 0, 1), (1, 2, 0, 1), (1, 1, 0, 0), (1, 1, float("nan"), 1)])
def test_invalid_aggregates(args):
    with pytest.raises(ValueError):
        score_provider(*args)


def test_bounds():
    r = score_provider(100, 100, 5, 0.01)
    assert all(0 <= r[k] <= 100 for k in ["quality", "outcome", "cost", "reliability", "volume"])


def test_specialty_ranking_and_ties():
    rows = [
        dict(provider_id=i, specialty=s, quality=q)
        for i, s, q in [(1, "A", 60), (2, "A", 60), (3, "A", 50), (4, "B", 40), (5, "A", None)]
    ]
    assert [r["rank"] for r in rank_specialties(rows)] == [1, 1, 3, 1, None]


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate_provider",
        "duplicate_encounter",
        "negative_cost",
        "missing_field",
        "unknown_provider",
        "bad_risk",
        "unknown_specialty",
    ],
)
def test_bad_batches(defect):
    ps, es = generate(5, 20)
    if defect == "duplicate_provider":
        ps.append(ps[0])
    if defect == "duplicate_encounter":
        es.append(es[0])
    if defect == "negative_cost":
        es[0]["cost"] = -1
    if defect == "missing_field":
        del es[0]["risk"]
    if defect == "unknown_provider":
        es[0]["provider_id"] = 999
    if defect == "bad_risk":
        es[0]["risk"] = float("inf")
    if defect == "unknown_specialty":
        ps[0]["specialty"] = "Fake"
    with pytest.raises(ValueError):
        validate(ps, es)


def test_missing_outcome_allowed():
    ps, es = generate(1, 1)
    es[0]["outcome"] = None
    assert validate(ps, es)["missing_outcomes"] == 1

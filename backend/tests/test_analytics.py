"""Portable SQL/API checks. PostgreSQL integration remains separately required."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import get_session
from app.main import app
from app.models import Base, Provider, Score
from app.scoring import score_provider


@pytest.fixture
def client(authenticated_reader):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        # Exact 80%, just below 80%, both thresholds failed, zero encounters,
        # missing materialization, 0% with encounters; plus >100 eligible points.
        cases = [(40, 32), (1001, 800), (20, 10), (0, 0), None, (50, 0)]
        cases += [(100, 95)] * 105
        for i, pair in enumerate(cases, 1):
            db.add(Provider(id=i, name=f"Provider {i}", specialty="Cardiology", location="Boston"))
            if pair is None:
                continue
            total, observed = pair
            parts = score_provider(total, observed, 0.02, 1.0)
            db.add(
                Score(
                    provider_id=i,
                    encounters=total,
                    observed=observed,
                    avg_cost=100 + i,
                    quality=parts["quality"],
                    rank=None,
                    components=parts,
                )
            )
        db.add(Provider(id=999, name="Other", specialty="Neurology", location="Boston"))
        db.commit()

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_all_eligible_cohort_and_sql_means(client):
    response = client.get("/api/analytics/quality-cost")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 106 > 100
    assert data["mean_cost"] == pytest.approx(sum(p["avg_cost"] for p in data["items"]) / 106)
    assert data["mean_score"] == pytest.approx(sum(p["quality"] for p in data["items"]) / 106)
    for p in data["items"]:
        assert p["highlighted"] == (p["quality"] > data["mean_score"] and p["avg_cost"] < data["mean_cost"])
    assert not {2, 3, 4, 5, 6, 999} & {p["id"] for p in data["items"]}


@pytest.mark.parametrize("specialty", ["Unknown", "Neurology", "' OR 1=1 --"])
def test_empty_cohort(client, specialty):
    data = client.get("/api/analytics/quality-cost", params={"specialty": specialty}).json()
    assert data["items"] == [] and data["count"] == 0
    assert data["mean_cost"] is None and data["mean_score"] is None


@pytest.mark.parametrize("specialty", ["", "x" * 51])
def test_invalid_specialty(client, specialty):
    assert client.get("/api/analytics/quality-cost", params={"specialty": specialty}).status_code == 422


def test_disjoint_evidence_and_exact_boundaries(client):
    data = client.get("/api/analytics/evidence").json()
    assert data["total"] == 112
    row = data["specialties"][0]
    assert row == dict(
        specialty="Cardiology", eligible=106, insufficient_outcomes=3, low_completeness=1, not_processed=1
    )
    assert sum(sum(v for k, v in r.items() if k != "specialty") for r in data["specialties"]) == 112
    bins = {b["name"]: b["count"] for b in data["completeness"]}
    assert sum(bins.values()) == 112
    assert bins["80–100%"] == 106
    assert bins["60–<80%"] == 1  # 800 / 1001 must not round into 80%.
    assert bins["No encounters"] == 1
    assert bins["Not processed"] == 2
    assert bins["0–<20%"] == 1


def test_empty_database(client):
    with next(app.dependency_overrides[get_session]()) as db:
        db.query(Score).delete()
        db.query(Provider).delete()
        db.commit()
    assert client.get("/api/analytics/evidence").json()["total"] == 0
    assert client.get("/api/analytics/quality-cost").json()["count"] == 0

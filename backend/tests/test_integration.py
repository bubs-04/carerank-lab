"""Use an explicitly designated disposable PostgreSQL database, never production."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from app.main import app
from app.db import get_session
from app.models import Provider, Encounter, Score, PipelineRun
from app.pipeline import run_pipeline
from app.generator import generate
from app import pipeline


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    target = make_url(url)
    if target.get_backend_name() != "postgresql" or target.database != "carerank_test":
        pytest.fail("Destructive integration tests require PostgreSQL database carerank_test")
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    from app.db import get_engine

    get_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    run_pipeline(100, 10000, engine=engine)
    yield engine
    engine.dispose()
    get_engine.cache_clear()
    if old:
        os.environ["DATABASE_URL"] = old
    else:
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def client(engine, authenticated_reader):
    def session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_counts_and_rerun(engine):
    run_pipeline(100, 10000, engine=engine)
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(Provider)) == 100
        assert c.scalar(select(func.count()).select_from(Encounter)) == 10000
        assert c.scalar(select(func.count()).select_from(Score)) == 100


def test_failed_validation_preserves_data(engine):
    ps, es = generate(5, 20)
    es.append(es[0])
    with pytest.raises(ValueError):
        run_pipeline(engine=engine, source=(ps, es))
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(Encounter)) == 10000
        assert (
            c.scalar(select(PipelineRun.status).order_by(PipelineRun.started_at.desc()).limit(1)) == "failed"
        )


def test_mid_transaction_failure_rolls_back(engine, monkeypatch):
    def fail(*args):
        raise RuntimeError("injected scoring failure")

    monkeypatch.setattr(pipeline, "score_provider", fail)
    with pytest.raises(RuntimeError):
        run_pipeline(5, 20, engine=engine)
    with engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(Provider)) == 100
        assert c.scalar(select(func.count()).select_from(Encounter)) == 10000


def test_sql_case_mix_and_nulls(engine):
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM encounters WHERE outcome IS NULL")) > 0
        row = c.execute(text("SELECT components FROM scores WHERE provider_id=1")).scalar_one()
        residual = c.scalar(text("SELECT avg(outcome-(0.95-0.30*risk)) FROM encounters WHERE provider_id=1"))
        assert row["residual"] == pytest.approx(residual, abs=1e-6)


def test_api_search_and_pagination(client):
    assert client.get("/api/health").status_code == 200
    a = client.get("/api/providers?specialty=Cardiology&page_size=3").json()
    b = client.get("/api/providers?specialty=Cardiology&page_size=3&page=2").json()
    assert a["total"] == 20 and len(a["items"]) == 3
    assert not {x["id"] for x in a["items"]} & {x["id"] for x in b["items"]}
    assert all(x["specialty"] == "Cardiology" for x in a["items"])
    assert client.get("/api/providers", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    assert client.get("/api/providers", params={"q": "%"}).json()["total"] == 0
    one = a["items"][0]
    assert client.get("/api/providers", params={"q": one["name"]}).json()["total"] == 1
    rows = client.get(
        "/api/providers",
        params={"location": one["location"], "min_quality": 40, "max_cost": 1000, "sort": "cost"},
    ).json()["items"]
    assert all(
        x["location"] == one["location"] and x["quality"] >= 40 and x["avg_cost"] <= 1000 for x in rows
    )
    assert [x["avg_cost"] for x in rows] == sorted(x["avg_cost"] for x in rows)


@pytest.mark.parametrize("query", ["page=0", "page_size=101", "min_quality=101", "max_cost=-1", "sort=DROP"])
def test_invalid_query(client, query):
    assert client.get("/api/providers?" + query).status_code == 422


def test_comparison_and_details(client):
    assert client.get("/api/providers/99999").status_code == 404
    assert client.get("/api/providers/1").status_code == 200
    assert client.get("/api/compare?ids=1&ids=6").status_code == 200
    assert client.get("/api/compare?ids=1&ids=2").status_code == 422
    assert client.get("/api/compare?ids=1&ids=1").status_code == 422
    assert client.get("/api/compare?ids=1&ids=99999").status_code == 404
    assert client.get("/api/compare?ids=1").status_code == 422


def test_analytics_and_openapi(client):
    a = client.get("/api/analytics").json()
    assert a["providers"] == 100 and a["encounters"] == 10000
    assert sum(x["count"] for x in a["distribution"]) == a["scored"]
    assert a["last_success"]["status"] == "success"
    assert client.get("/api/pipeline").json()
    assert "/api/compare" in client.get("/openapi.json").json()["paths"]


def test_zero_events_and_case_mix(engine):
    try:
        run_pipeline(5, 0, engine=engine)
        with engine.connect() as c:
            assert c.scalar(select(func.count()).select_from(Score).where(Score.quality.is_(None))) == 5
        ps, _ = generate(6, 0)
        ps = [ps[0], ps[5]]
        es = []
        for i in range(80):
            risk = 0.0 if i < 40 else 1.0
            es.append(
                dict(
                    id=i + 1,
                    provider_id=1 if i < 40 else 6,
                    procedure="Consultation",
                    risk=risk,
                    cost=100.0 * (1 + risk),
                    outcome=1,
                )
            )
        run_pipeline(engine=engine, source=(ps, es))
        with engine.connect() as c:
            parts = c.execute(select(Score.components).order_by(Score.provider_id)).scalars().all()
            assert parts[0]["cost_ratio"] == pytest.approx(1)
            assert parts[1]["cost_ratio"] == pytest.approx(1)
            assert parts[1]["outcome"] > parts[0]["outcome"]
    finally:
        run_pipeline(100, 10000, engine=engine)


def test_postgres_cohort_and_evidence(client, engine):
    cohort = client.get("/api/analytics/quality-cost?specialty=Cardiology").json()
    with Session(engine) as db:
        expected = db.scalar(
            select(func.count())
            .select_from(Provider)
            .join(Score)
            .where(Provider.specialty == "Cardiology", Score.quality.is_not(None))
        )
    assert cohort["count"] == len(cohort["items"]) == expected
    evidence = client.get("/api/analytics/evidence").json()
    assert evidence["total"] == 100
    assert sum(b["count"] for b in evidence["completeness"]) == 100
    assert sum(sum(v for k, v in r.items() if k != "specialty") for r in evidence["specialties"]) == 100


def test_registry_postgres_atomic_rerun(engine):
    from pathlib import Path
    from app.ingestion.connector import fixture_batch
    from app.ingestion.service import ingest
    from app.ingestion.models import Snapshot, IngestionRun

    fixture = Path(__file__).parent / "fixtures/cms_registry_a.csv"

    def fetch():
        return fixture_batch(fixture, 5)

    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Provider))
    first = ingest(engine, fetch, "fixture", 5)
    second = ingest(engine, fetch, "fixture", 5)
    with Session(engine) as db:
        assert db.get(IngestionRun, first).snapshot_id == db.get(IngestionRun, second).snapshot_id
        assert db.get(IngestionRun, second).status == "no_change"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1
        assert db.scalar(select(func.count()).select_from(Provider)) == before


def test_registry_postgres_concurrent_publication(engine):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from app.ingestion.connector import fixture_batch
    from app.ingestion.service import ingest
    from app.ingestion.models import IngestionRun

    fixture = Path(__file__).parent / "fixtures/cms_registry_b.csv"

    def execute(_):
        return ingest(engine, lambda: fixture_batch(fixture, 5), "fixture", 5)

    with ThreadPoolExecutor(max_workers=2) as workers:
        ids = list(workers.map(execute, range(2)))
    with Session(engine) as db:
        rows = [db.get(IngestionRun, i) for i in ids]
        assert rows[0].snapshot_id == rows[1].snapshot_id
        assert sorted(r.status for r in rows) == ["no_change", "succeeded"]


def test_monitoring_postgres_concurrency_and_audit_guard(engine, monkeypatch):
    """Real advisory locks, uniqueness and trigger enforcement; only on disposable TEST_DATABASE_URL."""
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from sqlalchemy.exc import DBAPIError
    from app.ingestion.connector import fixture_batch
    from app.ingestion.service import ingest
    from app.monitoring.service import evaluate_run, investigate
    from app.monitoring.models import Evaluation, Alert, AuditEvent

    monkeypatch.setenv("DQ_ENABLED", "false")
    fixture = Path(__file__).parent / "fixtures/cms_registry_a.csv"
    target = ingest(engine, lambda: fixture_batch(fixture, 5), "fixture", 5)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: evaluate_run(engine, target), range(2)))
    assert sorted(r["reused"] for r in results) == [False, True]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.run_id == target)) == 12
        )
        alert = db.scalar(select(Alert.id).where(Alert.run_id == target))

    def action(_):
        try:
            return investigate(
                engine, alert, actor="test", note="review", expected_revision=1, status="acknowledged"
            )["status"]
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(action, range(2))) == ["acknowledged", "conflict"]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == alert)) == 2
        )
    for operation in ("UPDATE monitor_events SET note='forbidden'", "DELETE FROM monitor_events"):
        with pytest.raises(DBAPIError), engine.begin() as db:
            db.execute(text(operation))


def test_monitoring_postgres_migration_preserves_existing_history(engine):
    from app.ingestion.models import Snapshot, IngestionRun, SourceRecord, SnapshotChange
    from sqlalchemy import inspect

    models = (Provider, Encounter, Score, Snapshot, IngestionRun, SourceRecord, SnapshotChange)

    def counts():
        with Session(engine) as db:
            return [db.scalar(select(func.count()).select_from(m)) for m in models]

    before = counts()
    command.downgrade(Config("alembic.ini"), "002")
    assert "monitor_alerts" not in inspect(engine).get_table_names()
    command.upgrade(Config("alembic.ini"), "head")
    assert before == counts()


def test_monitoring_postgres_evaluation_rollback(engine, monkeypatch):
    from pathlib import Path
    from app.ingestion.connector import fixture_batch
    from app.ingestion.service import ingest
    from app.monitoring.service import evaluate_run
    from app.monitoring.models import Evaluation, Alert

    monkeypatch.setenv("DQ_ENABLED", "false")
    target = ingest(
        engine, lambda: fixture_batch(Path(__file__).parent / "fixtures/cms_registry_a.csv", 5), "fixture", 5
    )

    def fail():
        raise RuntimeError("fault injection")

    with pytest.raises(RuntimeError):
        evaluate_run(engine, target, before_commit=fail)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.run_id == target)) == 0
        assert db.scalar(select(func.count()).select_from(Alert).where(Alert.run_id == target)) == 0

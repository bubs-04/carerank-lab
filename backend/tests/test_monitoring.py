"""Offline reliability cases. SQLite checks portability; PostgreSQL checks live separately."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session
from app.db import get_session
from app.main import app
from app.ingestion.connector import fixture_batch
from app.ingestion.models import RegistryBase, IngestionRun, Snapshot, SourceRecord
from app.ingestion.service import ingest, now
from app.ingestion.validation import BatchError
from app.monitoring.config import MonitoringSettings
from app.monitoring.models import Alert, AuditEvent, Evaluation, RuleVersion
from app.monitoring.rules import decide, definitions, profile_id
from app.monitoring.service import evaluate_run, investigate

FIXTURE = Path(__file__).parent / "fixtures/cms_registry_a.csv"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("DQ_ENABLED", "false")
    engine = create_engine("sqlite:///" + str(tmp_path / "monitor.sqlite"), connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def fk(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    RegistryBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def batch(scenario="normal"):
    b = fixture_batch(FIXTURE, 5)
    # Keep documented row identity; normalize only deterministic test records.
    b.rows[3]["npi"] = "1000000003"
    b.rows[-1].update(pri_spec="CARDIOLOGY", citytown="AUSTIN", state="TX")
    if scenario == "warning":
        b.rows[0]["pri_spec"] = ""
    elif scenario == "critical":
        b.rows[1] = dict(b.rows[0])
    elif scenario == "changed":
        b.rows[0]["pri_spec"] = "NEUROLOGY"
        b.rows[1]["adrs_id"] = "NEW_LOCATION"
    return b


def run(engine, scenario="normal"):
    return ingest(engine, lambda: batch(scenario), "fixture", 5)


def evaluations(engine, run_id):
    with Session(engine) as db:
        return {
            r.rule_id: e
            for e, r in db.execute(
                select(Evaluation, RuleVersion).join(RuleVersion).where(Evaluation.run_id == run_id)
            )
        }


@pytest.mark.parametrize(
    "metric, expected", [(0, "passed"), (5, "passed"), (5.00001, "failed"), (None, "not_evaluable")]
)
def test_threshold_boundary(metric, expected):
    rule = next(r for r in definitions(MonitoringSettings()) if r.rule_id == "rejected_rate")
    assert decide(rule, metric, {}, "missing evidence")["status"] == expected


def test_first_run_partial_then_all_rules_pass(engine):
    first = run(engine)
    evaluate_run(engine, first)
    first_results = evaluations(engine, first)
    assert len(first_results) == 12
    assert first_results["warning_change"].observed is None
    assert first_results["warning_change"].status == "not_evaluable"
    second = run(engine)
    evaluate_run(engine, second)
    assert all(e.status == "passed" for e in evaluations(engine, second).values())


@pytest.mark.parametrize(
    "scenario, rule, value, severity",
    [("warning", "missing_pri_spec", 20, "warning"), ("critical", "duplicate_rate", 40, "critical")],
)
def test_warning_and_critical_evidence(engine, scenario, rule, value, severity):
    run(engine)
    target = run(engine, scenario)
    evaluate_run(engine, target)
    e = evaluations(engine, target)[rule]
    assert e.status == "failed" and e.observed == value
    with Session(engine) as db:
        alert = db.scalar(select(Alert).where(Alert.evaluation_id == e.id))
        assert alert.severity == severity and alert.status == "open"
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == alert.id))
            == 1
        )


def test_comparison_denominators_warning_and_accepted_changes(engine):
    run(engine)
    changed = run(engine, "changed")
    evaluate_run(engine, changed)
    results = evaluations(engine, changed)
    assert results["added_rate"].observed == pytest.approx(100 / 6)
    assert results["removed_rate"].observed == pytest.approx(100 / 6)
    assert results["changed_rate"].observed == pytest.approx(100 / 6)
    assert "cutoff" in results["added_rate"].evidence["caveat"]
    critical = run(engine, "critical")
    evaluate_run(engine, critical)
    assert evaluations(engine, critical)["accepted_change"].observed == 40


@pytest.mark.parametrize("change", ["scope", "policy", "source", "overlap"])
def test_incompatible_history_is_not_a_baseline(engine, change):
    first = run(engine)
    with Session(engine) as db, db.begin():
        old = db.get(IngestionRun, first)
        snapshot = db.get(Snapshot, old.snapshot_id)
        if change == "scope":
            snapshot.scope_hash = "different"
        if change == "policy":
            snapshot.policy = "future-validation-policy"
        if change == "source":
            from app.ingestion.models import DataSource

            db.add(
                DataSource(
                    id="another-source",
                    dataset_id="other",
                    mode="fixture",
                    title="Other",
                    url="https://example.invalid",
                )
            )
            db.flush()
            old.source_id = snapshot.source_id = "another-source"
        if change == "overlap":
            old.finished_at = now() + timedelta(hours=1)
    second = run(engine, "warning")
    evaluate_run(engine, second)
    assert evaluations(engine, second)["accepted_change"].status == "not_evaluable"


@pytest.mark.parametrize(
    "code",
    [
        "incomplete_batch",
        "cms_transport_failure",
        "schema_missing_or_colliding_columns",
        "metadata_contract",
        "source_changed_during_download",
    ],
)
def test_failed_batch_never_means_zero_data_errors(engine, code):
    def fail():
        raise BatchError(code, 2)

    target = ingest(engine, fail, "fixture", 5)
    evaluate_run(engine, target)
    result = evaluations(engine, target)
    assert result["attempt_failure"].status == "failed"
    assert result["rejected_rate"].observed is None
    expected = "failed" if code.startswith(("schema", "metadata", "source")) else "not_evaluable"
    assert result["source_contract"].status == expected


def test_interrupted_attempt_and_stale_running(engine):
    def stop():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        ingest(engine, stop, "fixture", 5)
    with Session(engine) as db:
        target = db.scalar(select(IngestionRun.id))
    evaluate_run(engine, target)
    assert evaluations(engine, target)["attempt_failure"].observed == 1
    with Session(engine) as db, db.begin():
        db.get(IngestionRun, target).status = "running"
    assert evaluate_run(engine, target)["status"] == "pending"


def test_repeat_evaluation_and_changed_profile_do_not_duplicate_existing_rule_alerts(engine):
    target = run(engine, "critical")
    evaluate_run(engine, target)
    second = evaluate_run(engine, target)
    assert second["reused"]
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Alert))
    evaluate_run(engine, target, MonitoringSettings(membership_percent=40))
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == before
        assert db.scalar(select(func.count()).select_from(Evaluation)) == 24


def test_new_rule_threshold_preserves_prior_evidence(engine):
    target = run(engine, "warning")
    evaluate_run(engine, target)
    evaluate_run(engine, target, MonitoringSettings(missing_percent=30))
    with Session(engine) as db:
        rows = list(
            db.execute(
                select(Evaluation, RuleVersion)
                .join(RuleVersion)
                .where(RuleVersion.rule_id == "missing_pri_spec")
            )
        )
        assert {r.threshold for e, r in rows} == {5, 30}
        assert {e.status for e, r in rows} == {"passed", "failed"}


def test_evaluation_atomic_rollback(engine):
    target = run(engine, "critical")

    def fail():
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError):
        evaluate_run(engine, target, before_commit=fail)
    with Session(engine) as db:
        for model in (Evaluation, Alert, AuditEvent, RuleVersion):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.get(IngestionRun, target).status == "succeeded"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1


def test_concurrent_evaluation_on_portable_database(engine):
    target = run(engine, "critical")
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: evaluate_run(engine, target), range(2)))
    assert sorted(r["reused"] for r in results) == [False, True]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Evaluation)) == 12
        assert db.scalar(select(func.count()).select_from(Alert)) == db.scalar(
            select(func.count()).select_from(AuditEvent)
        )


def first_alert(engine):
    target = run(engine, "critical")
    evaluate_run(engine, target)
    with Session(engine) as db:
        return db.scalar(select(Alert.id))


def test_lifecycle_audit_resolution_reopen_and_assignment(engine):
    alert = first_alert(engine)
    for revision, status in enumerate(["acknowledged", "investigating", "resolved", "open"], 1):
        result = investigate(
            engine,
            alert,
            actor="local-reviewer",
            note="Reviewed prefix evidence",
            expected_revision=revision,
            status=status,
            assignee="owner",
        )
        assert result["revision"] == revision + 1
    with Session(engine) as db:
        a = db.get(Alert, alert)
        events = list(
            db.scalars(select(AuditEvent).where(AuditEvent.alert_id == alert).order_by(AuditEvent.revision))
        )
        assert a.status == "open" and a.resolution is None and a.assigned_to == "owner"
        assert [e.revision for e in events] == [1, 2, 3, 4, 5]
        assert events[3].note == "Reviewed prefix evidence"


@pytest.mark.parametrize(
    "kwargs",
    [{"status": "resolved"}, {"expected_revision": 7}, {"actor": ""}, {"note": ""}, {"status": "open"}],
)
def test_invalid_investigation_no_audit_change(engine, kwargs):
    alert = first_alert(engine)
    args = dict(actor="local", note="check", expected_revision=1)
    args.update(kwargs)
    with pytest.raises(ValueError):
        investigate(engine, alert, **args)
    with Session(engine) as db:
        assert db.get(Alert, alert).revision == 1


def test_triage_rollback_and_concurrent_decisions(engine):
    alert = first_alert(engine)

    def fail():
        raise RuntimeError("fault")

    with pytest.raises(RuntimeError):
        investigate(
            engine, alert, actor="a", note="x", expected_revision=1, status="acknowledged", before_commit=fail
        )

    def action(_):
        try:
            return investigate(
                engine, alert, actor="a", note="x", expected_revision=1, status="investigating"
            )["status"]
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(action, range(2))) == ["conflict", "investigating"]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == alert)) == 2
        )


def test_automatic_evaluation_and_failure_isolation(engine, monkeypatch):
    monkeypatch.setenv("DQ_ENABLED", "true")
    target = run(engine)
    assert len(evaluations(engine, target)) == 12
    import app.monitoring.service as service

    def fail(*args):
        raise RuntimeError("monitor down")

    monkeypatch.setattr(service, "evaluate_run", fail)
    target = run(engine, "changed")
    with Session(engine) as db:
        assert db.get(IngestionRun, target).status == "succeeded"
    assert not evaluations(engine, target)


@pytest.fixture
def client(engine, monkeypatch, authenticated_reader):
    monkeypatch.setenv("DQ_ENABLED", "true")

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_health_requires_evidence_and_current_profile(engine, client, monkeypatch):
    url = "/api/dataops/monitoring/summary?mode=fixture"
    assert client.get(url).json()["health"] == "no_data"
    run(engine)
    assert client.get(url).json()["health"] == "partial"
    target = run(engine)
    assert client.get(url).json()["health"] == "passed"
    monkeypatch.setenv("DQ_MISSING_PERCENT", "30")
    assert client.get(url).json()["health"] == "pending"
    evaluate_run(engine, target)
    assert client.get(url).json()["health"] == "passed"
    monkeypatch.setenv("DQ_ENABLED", "false")
    assert client.get(url).json()["health"] == "disabled"


def test_api_read_only_filters_evidence_and_history(engine, client):
    target = run(engine, "critical")
    prefix = "/api/dataops/monitoring"
    assert client.get(prefix + "/summary?mode=fixture").json()["health"] == "attention"
    alerts = client.get(prefix + "/alerts?mode=fixture&severity=critical&status=open").json()
    assert alerts["total"] == 1
    alert = alerts["items"][0]["id"]
    detail = client.get(prefix + f"/alerts/{alert}").json()
    assert detail["evaluation"]["rule"]["rule_id"] == "duplicate_rate"
    assert detail["evaluation"]["evidence"]["duplicate_rate_rows"] == 2
    assert client.get(prefix + f"/alerts/{alert}/events").json()["total"] == 1
    assert client.get(prefix + "/alerts?mode=cms").json()["total"] == 0
    assert client.get(prefix + f"/runs/{target}").json()["received"] == 5
    assert len(client.get(prefix + "/rules").json()) == 12
    assert client.get(prefix + "/evaluations?mode=fixture&page_size=2").json()["total"] == 12
    for verb in ("post", "patch", "put", "delete"):
        assert (
            getattr(client, verb)(prefix + f"/alerts/{alert}", headers={"X-User": "admin"}).status_code == 405
        )
    assert client.get(prefix + "/alerts/missing").status_code == 404
    assert client.get(prefix + "/alerts?page_size=101").status_code == 422


def test_trends_are_scope_filtered_and_bounded(engine, client):
    first = run(engine)
    run(engine, "warning")
    with Session(engine) as db, db.begin():
        db.get(Snapshot, db.get(IngestionRun, first).snapshot_id).scope_hash = "different"
    result = client.get("/api/dataops/monitoring/trends?mode=fixture&limit=1").json()
    assert len(result["points"]) == 1
    assert result["points"][0]["valid"] == 5
    assert client.get("/api/dataops/monitoring/trends?mode=cms&run_id=" + first).status_code == 422


def test_migration_audit_immutability_and_registry_preservation(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlalchemy.exc import DBAPIError
    from app.db import get_engine

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "carerank_test"))
    monkeypatch.setenv("DQ_ENABLED", "false")
    get_engine.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "002")
        engine = get_engine()
        target = run(engine)
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO providers (id,name,specialty,location) VALUES (1,'Synthetic sentinel','Cardiology','Boston')"
                )
            )
        command.upgrade(config, "head")
        first_alert(engine)
        for operation in ("UPDATE monitor_events SET note='tampered'", "DELETE FROM monitor_events"):
            with pytest.raises(DBAPIError), engine.begin() as db:
                db.execute(text(operation))
        command.downgrade(config, "002")
        assert "monitor_alerts" not in inspect(engine).get_table_names()
        with Session(engine) as db:
            assert db.get(IngestionRun, target).status == "succeeded"
            assert db.scalar(select(func.count()).select_from(SourceRecord)) == 10
            assert db.scalar(text("SELECT count(*) FROM providers")) == 1
        command.upgrade(config, "head")
        assert evaluate_run(engine, target)["counts"]["not_evaluable"] == 5
    finally:
        get_engine().dispose()
        get_engine.cache_clear()


def test_config_identity_and_invalid_thresholds():
    from pydantic import ValidationError

    assert profile_id(definitions(MonitoringSettings())) == profile_id(definitions(MonitoringSettings()))
    for number in (-1, float("nan"), float("inf"), 101):
        with pytest.raises(ValidationError):
            MonitoringSettings(rejected_percent=number)


def test_invalid_api_configuration_is_explained_without_secret_values(engine, client, monkeypatch):
    monkeypatch.setenv("DQ_REJECTED_PERCENT", "not-a-number")
    response = client.get("/api/dataops/monitoring/summary")
    assert response.status_code == 503
    assert response.json()["detail"] == "Monitoring configuration invalid. Check DQ_ environment variables."
    assert "not-a-number" not in response.text


def test_record_count_mismatch_is_not_complete_evidence(engine):
    target = run(engine)
    with Session(engine) as db, db.begin():
        row = db.scalar(
            select(SourceRecord).where(SourceRecord.snapshot_id == db.get(IngestionRun, target).snapshot_id)
        )
        db.delete(row)
    evaluate_run(engine, target)
    result = evaluations(engine, target)
    assert result["rejected_rate"].status == "not_evaluable"
    assert result["duplicate_rate"].observed is None


def test_warning_rate_delta_is_findings_not_rejected_rows(engine):
    run(engine)
    target = run(engine, "warning")
    evaluate_run(engine, target)
    result = evaluations(engine, target)
    assert result["warning_change"].observed == 20
    assert result["rejected_rate"].observed == 0
    assert result["warning_change"].evidence["baseline_warnings"] == 0


def test_schema_warning_is_explicit_contract_signal(engine):
    def fetch():
        b = batch()
        b.headers.append("unexpected_future_column")
        return b

    target = ingest(engine, fetch, "fixture", 5)
    evaluate_run(engine, target)
    result = evaluations(engine, target)["source_contract"]
    assert result.status == "failed" and result.observed == 1
    assert result.evidence["source_contract_findings"] == {"new_column": 1}


def test_cli_backfill_progresses_and_skips_completed_profiles(engine, monkeypatch):
    import sys
    from app.monitoring import __main__ as cli

    first, second = run(engine), run(engine, "warning")
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    monkeypatch.setattr(sys, "argv", ["monitoring", "evaluate", "--mode", "fixture", "--limit", "1"])
    cli.main()
    assert len(evaluations(engine, first)) == 12 and not evaluations(engine, second)
    cli.main()
    assert len(evaluations(engine, second)) == 12
    cli.main()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Evaluation)) == 24

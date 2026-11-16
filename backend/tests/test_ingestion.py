"""Deterministic CSV -> validation -> transaction -> comparison -> API tests."""

import io
import os
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import get_session
from app.main import app
from app.ingestion.config import IngestionSettings
from app.ingestion.connector import CMSConnector, fixture_batch, metadata_provenance, parse_rows
from app.ingestion.validation import BatchError, validate, FIELDS
from app.ingestion.models import (
    RegistryBase,
    Snapshot,
    IngestionRun,
    SourceRecord,
    ValidationFinding,
    SnapshotChange,
)
from app.ingestion.service import ingest
from app.ingestion.compare import compare_records, compare_versions

FIXTURES = Path(__file__).parent / "fixtures"


def batch(name="a"):
    return fixture_batch(FIXTURES / f"cms_registry_{name}.csv", 5)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    RegistryBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def snapshot_for(engine, run_id):
    with Session(engine) as db:
        return db.get(IngestionRun, run_id).snapshot_id


def test_fixture_validation_and_preserved_granularity():
    import hashlib

    b = batch()
    assert (
        b.provenance["fixture_sha256"]
        == hashlib.sha256((FIXTURES / "cms_registry_a.csv").read_bytes()).hexdigest()
    )
    result = validate(b.rows, b.headers)
    assert (result.valid, result.rejected, result.warnings) == (4, 1, 3)
    assert result.records[0]["record_key"] != result.records[1]["record_key"]
    assert all(set(r["data"]) == set(FIELDS) for r in result.records)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("npi", "", "missing_identifier"),
        ("npi", "123", "invalid_identifier"),
        ("ind_enrl_id", "x", "invalid_identifier"),
        ("org_pac_id", "x", "invalid_identifier"),
        ("adrs_id", "", "missing_identifier"),
        ("state", "ZZ", "invalid_state"),
        ("citytown", "x" * 31, "invalid_length"),
        ("pri_spec", "x" * 61, "invalid_length"),
        ("citytown", "A\x00B", "control_character"),
    ],
)
def test_invalid_record(field, value, code):
    b = batch()
    b.rows[0][field] = value
    result = validate(b.rows, b.headers)
    assert not result.records[0]["accepted"]
    assert any(f["row_number"] == 1 and f["code"] == code for f in result.findings)


def test_duplicate_identity_rejects_all_occurrences():
    b = batch()
    b.rows[2] = dict(b.rows[0])
    b.rows[2]["pri_spec"] = "OTHER"
    result = validate(b.rows, b.headers)
    assert not result.records[0]["accepted"] and not result.records[2]["accepted"]
    assert sum(f["code"] == "duplicate_identity" for f in result.findings) == 2


def test_schema_addition_warning_and_missing_column_failure():
    b = batch()
    assert validate(b.rows, b.headers + ["future_column"]).findings[0]["code"] == "new_column"
    with pytest.raises(BatchError, match="schema"):
        validate(b.rows, b.headers[1:])


def test_empty_and_truncated_csv():
    with pytest.raises(BatchError):
        parse_rows(io.StringIO(""), 5)
    with pytest.raises(BatchError, match="incomplete"):
        parse_rows(io.StringIO((FIXTURES / "cms_registry_a.csv").read_text()), 6)
    with pytest.raises(BatchError, match="malformed_csv_row"):
        parse_rows(io.StringIO(",".join(FIELDS) + "\nonly,2\n"), 1)


def test_safe_rerun_and_real_projection_storage(engine):
    first = ingest(engine, batch, "fixture", 5)
    second = ingest(engine, batch, "fixture", 5)
    assert snapshot_for(engine, first) == snapshot_for(engine, second)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1
        assert db.scalar(select(func.count()).select_from(SourceRecord)) == 5
        assert db.get(IngestionRun, second).status == "no_change"
        assert db.scalar(select(func.count()).select_from(ValidationFinding)) == 8


def test_comparison_and_stored_summary(engine):
    a = ingest(engine, batch, "fixture", 5)
    b = ingest(engine, lambda: batch("b"), "fixture", 5)
    with Session(engine) as db:
        result = compare_versions(db, snapshot_for(engine, a), snapshot_for(engine, b))
        assert [result[k] for k in ("added", "removed", "changed", "unchanged")] == [1, 1, 1, 2]
        assert result["specialty_changes"] == result["location_changes"] == 1
        assert all(v == 0 for v in result["validation_delta"].values())
        assert db.scalar(select(SnapshotChange)).summary == result
        reverse = compare_versions(db, snapshot_for(engine, b), snapshot_for(engine, a))
        assert reverse["examples"][0]["before"] == result["examples"][0]["after"]


@pytest.mark.parametrize("failure", [BatchError("cms_transport_failure"), RuntimeError("DO NOT LEAK SECRET")])
def test_failure_preserves_success(engine, failure):
    first = ingest(engine, batch, "fixture", 5)

    def fail():
        raise failure

    failed = ingest(engine, fail, "fixture", 5)
    with Session(engine) as db:
        assert db.get(IngestionRun, failed).status == "failed"
        assert db.get(IngestionRun, failed).snapshot_id is None
        assert db.get(IngestionRun, first).status == "succeeded"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1
        assert "SECRET" not in str(db.get(IngestionRun, failed).error_code)


def test_transaction_failure_rolls_back_records_findings_and_version(engine):
    first = ingest(engine, batch, "fixture", 5)

    def fail():
        raise RuntimeError("injected commit-boundary fault")

    failed = ingest(engine, lambda: batch("b"), "fixture", 5, before_commit=fail)
    with Session(engine) as db:
        assert db.get(IngestionRun, failed).status == "failed"
        assert db.get(IngestionRun, failed).snapshot_id is None
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1
        assert db.scalar(select(func.count()).select_from(SourceRecord)) == 5
        assert db.scalar(select(func.count()).select_from(SnapshotChange)) == 0
        assert snapshot_for(engine, first)


def test_interruption_has_no_partial_snapshot(engine):
    def interrupt():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        ingest(engine, interrupt, "fixture", 5)
    with Session(engine) as db:
        assert db.scalar(select(IngestionRun.status)) == "interrupted"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_all_invalid_has_findings_but_no_snapshot(engine):
    def invalid():
        b = batch()
        for r in b.rows:
            r["npi"] = ""
        return b

    run = ingest(engine, invalid, "fixture", 5)
    with Session(engine) as db:
        assert db.get(IngestionRun, run).rejected == 5
        assert db.get(IngestionRun, run).error_code == "no_valid_records"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_comparison_requires_compatible_scope(engine):
    a = ingest(engine, batch, "fixture", 5)

    def small():
        return fixture_batch(FIXTURES / "cms_registry_a.csv", 2)

    b = ingest(engine, small, "fixture", 2)
    with Session(engine) as db:
        with pytest.raises(ValueError):
            compare_versions(db, snapshot_for(engine, a), snapshot_for(engine, b))


def test_duplicate_accepted_identity_never_silently_overwrites():
    r = validate(batch().rows, batch().headers).records[0]
    with pytest.raises(ValueError):
        compare_records([r, r], [r])


def metadata(url="https://data.cms.gov/provider-data/sites/default/files/resources/release.csv"):
    return {
        "identifier": "mj5m-pzi6",
        "accessLevel": "public",
        "released": "2026-01-01",
        "modified": "2026-01-01",
        "distribution": [{"identifier": "release-1", "data": {"downloadURL": url}}],
    }


def test_network_connector_uses_official_metadata_and_bounded_projection():
    requests = []

    def handler(request):
        requests.append(request.url)
        if "/metastore/" in request.url.path:
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, content=(FIXTURES / "cms_registry_a.csv").read_bytes())

    result = CMSConnector(IngestionSettings(max_rows=5), httpx.MockTransport(handler)).fetch()
    assert len(result.rows) == 5 and len(requests) == 3
    assert result.provenance["release"] == "2026-01-01"


@pytest.mark.parametrize(
    "url",
    [
        "http://data.cms.gov/a.csv",
        "https://evil.test/a.csv",
        "https://data.cms.gov@evil.test/a.csv",
        "https://data.cms.gov/private.csv",
    ],
)
def test_metadata_cannot_redirect_to_arbitrary_hosts(url):
    with pytest.raises(BatchError):
        metadata_provenance(metadata(url))


def test_retry_is_bounded_and_restarts_download():
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(BatchError, match="cms_http_503"):
        CMSConnector(IngestionSettings(attempts=3), httpx.MockTransport(handler), sleeps.append).fetch()
    assert len(calls) == 3 and sleeps == [1, 2]


def test_release_changed_during_download_rejected():
    count = 0

    def handler(request):
        nonlocal count
        if "/metastore/" in request.url.path:
            count += 1
            m = metadata()
            m["modified"] = str(count)
            return httpx.Response(200, json=m)
        return httpx.Response(200, content=(FIXTURES / "cms_registry_a.csv").read_bytes())

    with pytest.raises(BatchError, match="source_changed"):
        CMSConnector(IngestionSettings(max_rows=5), httpx.MockTransport(handler)).fetch()


def test_readonly_api_and_pagination(engine):
    run = ingest(engine, batch, "fixture", 5)

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            assert client.get("/api/dataops/status").json()["latest_success"] is None
            assert client.get("/api/dataops/status?mode=fixture").json()["latest_success"]["id"] == run
            v = client.get("/api/dataops/versions?mode=fixture").json()["items"][0]
            assert client.get(f"/api/dataops/versions/{v['id']}/records?page_size=2").json()["total"] == 5
            assert client.get(f"/api/dataops/runs/{run}/findings?page_size=1").json()["total"] == 4
            assert client.get("/api/dataops/versions?page=0").status_code == 422
            assert client.get("/api/dataops/compare?old_id=missing&new_id=missing").status_code == 404
            assert client.post("/api/dataops/status").status_code == 405
            assert client.get("/api/dataops/runs/missing/findings").status_code == 404
            paths = client.get("/openapi.json").json()["paths"]
            assert all(
                set(methods) == {"get"} for path, methods in paths.items() if path.startswith("/api/dataops")
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(
    os.environ.get("CMS_LIVE_TEST") != "1", reason="Opt-in live CMS retrieval; no network in default CI"
)
def test_live_cms_optional():
    result = CMSConnector(IngestionSettings(max_rows=1000)).fetch()
    assert len(result.rows) == 1000
    assert validate(result.rows, result.headers).valid > 0


def test_missing_and_blank_values_are_not_schema_failure():
    b = batch()
    assert validate(b.rows, b.headers).records[-1]["accepted"]
    b.rows[0]["npi"] = None
    result = validate(b.rows, b.headers)
    assert any(f["code"] == "invalid_type" for f in result.findings)


def test_download_interruption_retry_never_publishes_partial(engine):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield (FIXTURES / "cms_registry_a.csv").read_bytes()[:150]
            raise httpx.ReadError("interrupted")

    def handler(request):
        if "/metastore/" in request.url.path:
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, stream=Interrupted())

    connector = CMSConnector(
        IngestionSettings(max_rows=5, attempts=2), httpx.MockTransport(handler), lambda _: None
    )
    run = ingest(engine, connector.fetch, "cms", 5)
    with Session(engine) as db:
        audit = db.get(IngestionRun, run)
        assert audit.status == "failed" and audit.error_code == "cms_transport_failure"
        assert audit.provenance["release"] == "2026-01-01"
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_byte_limit_and_multiline_csv():
    def handler(request):
        if "/metastore/" in request.url.path:
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, content=b"x" * 2000)

    with pytest.raises(BatchError, match="byte_limit"):
        CMSConnector(IngestionSettings(max_bytes=1000), httpx.MockTransport(handler)).fetch()
    b = batch()
    text = ",".join(FIELDS) + "\n" + ",".join('"A\nB"' if k == "citytown" else b.rows[0][k] for k in FIELDS)
    rows, headers = parse_rows(io.StringIO(text), 1)
    assert rows[0]["citytown"] == "A\nB"
    assert not validate(rows, headers).records[0]["accepted"]


def test_validation_differences_are_explainable(engine):
    first = ingest(engine, batch, "fixture", 5)

    def repaired():
        b = batch()
        b.rows[-1].update(pri_spec="CARDIOLOGY", citytown="AUSTIN", state="TX")
        return b

    second = ingest(engine, repaired, "fixture", 5)
    with Session(engine) as db:
        result = compare_versions(db, snapshot_for(engine, first), snapshot_for(engine, second))
        assert result["validation_delta"]["missing_optional"] == -3
        assert result["changed"] == 1


def test_reverted_content_reuses_version_and_next_diff_uses_last_retrieval(engine):
    first = ingest(engine, batch, "fixture", 5)
    ingest(engine, lambda: batch("b"), "fixture", 5)
    reverted = ingest(engine, batch, "fixture", 5)

    def changed():
        b = batch()
        b.rows[0]["pri_spec"] = "ENDOCRINOLOGY"
        return b

    latest = ingest(engine, changed, "fixture", 5)
    with Session(engine) as db:
        assert snapshot_for(engine, reverted) == snapshot_for(engine, first)
        saved = db.scalar(select(SnapshotChange).where(SnapshotChange.new_id == snapshot_for(engine, latest)))
        assert saved.old_id == snapshot_for(engine, reverted)


def test_registry_migration_roundtrip_preserves_synthetic_data(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text
    from app.db import get_engine

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "migration.sqlite"))
    get_engine.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "001")
        with get_engine().begin() as db:
            db.execute(
                text(
                    "INSERT INTO providers (id,name,specialty,location) VALUES (1,'Synthetic sentinel','Cardiology','Boston')"
                )
            )
        command.upgrade(config, "head")
        assert "registry_snapshots" in inspect(get_engine()).get_table_names()
        command.downgrade(config, "001")
        assert "registry_snapshots" not in inspect(get_engine()).get_table_names()
        with get_engine().connect() as db:
            assert db.scalar(text("SELECT count(*) FROM providers")) == 1
        command.upgrade(config, "head")
    finally:
        get_engine().dispose()
        get_engine.cache_clear()


def test_reordered_capture_keeps_findings_aligned_and_diff_is_unchanged(engine):
    first = ingest(engine, batch, "fixture", 5)

    def reordered():
        b = batch()
        b.rows.reverse()
        return b

    second = ingest(engine, reordered, "fixture", 5)
    assert snapshot_for(engine, first) != snapshot_for(engine, second)
    with Session(engine) as db:
        result = compare_versions(db, snapshot_for(engine, first), snapshot_for(engine, second))
        assert result["unchanged"] == 4 and result["changed"] == 0
        findings = list(db.scalars(select(ValidationFinding).where(ValidationFinding.run_id == second)))
        assert any(f.row_number == 2 and f.code == "invalid_identifier" for f in findings)


def test_permanent_http_failure_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403)

    with pytest.raises(BatchError, match="cms_http_403"):
        CMSConnector(IngestionSettings(), httpx.MockTransport(handler)).fetch()
    assert len(calls) == 1


def test_deadline_during_metadata(monkeypatch):
    from app.ingestion import connector

    ticks = iter([0, 11])
    monkeypatch.setattr(connector.time, "monotonic", lambda: next(ticks))
    with pytest.raises(BatchError, match="deadline_exceeded"):
        CMSConnector(
            IngestionSettings(deadline_seconds=10),
            httpx.MockTransport(lambda r: httpx.Response(200, json=metadata())),
        ).fetch()

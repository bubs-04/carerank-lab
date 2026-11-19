"""Offline archive validation uses artificial rows; never claims a live CMS retrieval."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy.engine import make_url
from app.demo import guard
from app.ingestion.archive import archive_document, read_archive
from app.ingestion.config import DATASET, METADATA_URL
from app.ingestion.connector import fixture_batch
from app.ingestion.validation import BatchError, digest


def document():
    batch = fixture_batch(Path(__file__).parent / "fixtures/cms_registry_a.csv", 5)
    # Contract-only mocked provenance. This document is never shipped as CMS data.
    batch.provenance = {
        "mode": "cms",
        "dataset_id": DATASET,
        "metadata_url": METADATA_URL,
        "download_url": "https://data.cms.gov/provider-data/sites/default/files/test.csv",
        "retrieval_method": "bounded_csv_stream",
    }
    return archive_document(batch, datetime.now(timezone.utc).isoformat())


def test_archive_replay_is_explicit_and_preserves_verified_scope(tmp_path):
    path = tmp_path / "archive.json"
    source = document()
    path.write_text(json.dumps(source))
    batch = read_archive(path)
    assert batch.rows == source["rows"] and batch.scope == source["scope"]
    assert batch.provenance["archive_replay"] is True
    assert batch.provenance["fresh_live_retrieval"] is False
    assert batch.provenance["archive_payload_sha256"] == source["payload_sha256"]


@pytest.mark.parametrize("case", ["checksum", "host", "credentials", "fields", "scope", "future"])
def test_archive_rejects_corruption_or_invalid_source_even_with_recomputed_checksum(tmp_path, case):
    source = document()
    if case == "checksum":
        source["rows"][0]["state"] = "ZZ"
    else:
        if case == "host":
            source["provenance"]["download_url"] = "https://attacker.example/test.csv"
        elif case == "credentials":
            source["provenance"]["download_url"] = (
                "https://u:p@data.cms.gov/provider-data/sites/default/files/test.csv"
            )
        elif case == "fields":
            source["rows"][0]["patient_name"] = "forbidden"
        elif case == "scope":
            source["scope"]["max_rows"] = 999
        else:
            source["captured_at"] = "2999-01-01T00:00:00+00:00"
        source.pop("payload_sha256")
        source["payload_sha256"] = digest(source)
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(source))
    with pytest.raises(BatchError, match="invalid_cms_archive"):
        read_archive(path)


@pytest.mark.parametrize(
    "url,environment",
    [
        ("postgresql+psycopg://carerank_demo_owner@127.0.0.1/carerank", "development"),
        ("postgresql+psycopg://carerank_demo_owner@127.0.0.1/carerank_demo", "production"),
        ("postgresql+psycopg://owner@127.0.0.1/carerank_demo", "development"),
        ("postgresql+psycopg://carerank_demo_owner@remote/carerank_demo", "development"),
    ],
)
def test_demo_guard_rejects_retained_or_remote_databases(monkeypatch, url, environment):
    monkeypatch.setenv("APP_ENV", environment)
    with pytest.raises(ValueError):
        guard(SimpleNamespace(url=make_url(url)))


@pytest.fixture
def archive_engine():
    from sqlalchemy import create_engine
    from app.ingestion.models import RegistryBase
    import app.monitoring.models  # noqa: F401

    engine = create_engine("sqlite://")
    RegistryBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def archive_batch(tmp_path):
    path = tmp_path / "mock-public-source-contract.json"
    path.write_text(json.dumps(document()))
    return read_archive(path)


def test_failed_archive_attempt_is_preserved_and_retried_until_published(archive_engine, tmp_path):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from app.demo import load_archive, archive_published
    from app.ingestion.models import IngestionRun, Snapshot
    from app.ingestion.service import ingest

    batch = archive_batch(tmp_path)

    def failure():
        raise RuntimeError("harmless publication failure")

    failed = ingest(archive_engine, lambda: batch, "cms", 5, before_commit=failure)
    with Session(archive_engine) as db:
        row = db.get(IngestionRun, failed)
        assert row.status == "failed" and row.provenance["archive_payload_sha256"]
        assert not archive_published(db, batch.provenance["archive_payload_sha256"])
    assert load_archive(archive_engine, batch)
    assert load_archive(archive_engine, batch)
    with Session(archive_engine) as db:
        assert db.get(IngestionRun, failed).status == "failed"
        assert db.scalar(select(func.count()).select_from(IngestionRun)) == 2
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1


@pytest.mark.parametrize("status", ["running", "succeeded", "no_change"])
def test_checksum_without_publication_link_never_suppresses_retry(archive_engine, tmp_path, status):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from app.demo import load_archive, archive_published
    from app.ingestion.models import IngestionRun, Snapshot
    from app.ingestion.service import ingest

    batch = archive_batch(tmp_path)
    incomplete = ingest(archive_engine, lambda: batch, "cms", 5)
    with Session(archive_engine) as db, db.begin():
        row = db.get(IngestionRun, incomplete)
        row.status, row.snapshot_id = status, None
    with Session(archive_engine) as db:
        assert not archive_published(db, batch.provenance["archive_payload_sha256"])
    assert load_archive(archive_engine, batch)
    assert load_archive(archive_engine, batch)
    with Session(archive_engine) as db:
        rows = list(db.scalars(select(IngestionRun)))
        assert len(rows) == 2
        assert any(row.status == "no_change" and row.snapshot_id for row in rows)
        assert db.get(IngestionRun, incomplete).snapshot_id is None
        assert db.scalar(select(func.count()).select_from(Snapshot)) == 1

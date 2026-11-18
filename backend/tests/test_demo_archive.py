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

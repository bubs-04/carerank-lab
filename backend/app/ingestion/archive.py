"""Capture a bounded official CMS response once; replay its verified bytes offline.

A checksum detects corruption, not authenticity. Archives must be operator-captured
through the fixed HTTPS connector and reviewed before distribution.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

from .config import DATASET, METADATA_URL, IngestionSettings
from .connector import Batch, CMSConnector, scope_for
from .validation import BatchError, FIELDS, canonical, digest, validate

MAX_ARCHIVE_BYTES = 1_000_000


def archive_document(batch: Batch, captured_at: str) -> dict:
    payload = {
        "schema_version": 1,
        "captured_at": captured_at,
        "headers": batch.headers,
        "rows": batch.rows,
        "provenance": batch.provenance,
        "scope": batch.scope,
    }
    return {**payload, "payload_sha256": digest(payload)}


def read_archive(path: Path) -> Batch:
    try:
        with path.open("rb") as file:
            raw = file.read(MAX_ARCHIVE_BYTES + 1)
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ValueError()
        document = json.loads(raw)
        checksum = document.pop("payload_sha256")
        if set(document) != {"schema_version", "captured_at", "headers", "rows", "provenance", "scope"}:
            raise ValueError()
        if document["schema_version"] != 1 or checksum != digest(document):
            raise ValueError()
        captured = datetime.fromisoformat(document["captured_at"])
        if captured.tzinfo is None or captured > datetime.now(timezone.utc):
            raise ValueError()
        rows, headers, provenance = document["rows"], document["headers"], document["provenance"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
            raise ValueError()
        if (
            not isinstance(headers, list)
            or len(headers) > 100
            or not all(isinstance(h, str) for h in headers)
        ):
            raise ValueError()
        if any(not isinstance(row, dict) or set(row) != set(FIELDS) for row in rows):
            raise ValueError()
        if provenance.get("mode") != "cms" or provenance.get("dataset_id") != DATASET:
            raise ValueError()
        if provenance.get("metadata_url") != METADATA_URL:
            raise ValueError()
        url = urlparse(provenance["download_url"])
        if (
            url.scheme != "https"
            or url.hostname != "data.cms.gov"
            or url.port not in (None, 443)
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not url.path.startswith("/provider-data/sites/default/files/")
            or not url.path.endswith(".csv")
        ):
            raise ValueError()
        if provenance.get("retrieval_method") != "bounded_csv_stream":
            raise ValueError()
        if document["scope"] != scope_for(len(rows)) or validate(rows, headers).valid == 0:
            raise ValueError()
        return Batch(
            rows,
            headers,
            {
                **provenance,
                "retrieval_method": "verified_offline_cms_archive",
                "archive_captured_at": captured.isoformat(),
                "archive_payload_sha256": checksum,
                "archive_replay": True,
                "fresh_live_retrieval": False,
            },
            document["scope"],
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError, BatchError):
        raise BatchError("invalid_cms_archive") from None


def capture(path: Path, count: int = 25):
    batch = CMSConnector(IngestionSettings(max_rows=count)).fetch()
    payload = canonical(archive_document(batch, datetime.now(timezone.utc).isoformat()))
    if len(payload.encode()) > MAX_ARCHIVE_BYTES:
        raise BatchError("archive_byte_limit")
    # Refuse overwriting an existing reviewed archive.
    with path.open("x") as file:
        file.write(payload + "\n")
    read_archive(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["capture", "verify"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--rows", type=int, default=25, choices=range(1, 501), metavar="1..500")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            capture(args.path, args.rows)
        batch = read_archive(args.path)
        print(canonical({"rows": len(batch.rows), "provenance": batch.provenance}))
        return 0
    except (BatchError, OSError) as exc:
        print(canonical({"error_code": exc.code if isinstance(exc, BatchError) else "archive_file_error"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

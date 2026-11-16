"""Real CMS metadata + bounded streaming CSV connector; fixtures use the same parser."""

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .config import DATASET, METADATA_URL, IngestionSettings
from .validation import BatchError, FIELDS, header_name, digest


@dataclass
class Batch:
    rows: list[dict]
    headers: list[str]
    provenance: dict
    scope: dict


def parse_rows(lines, max_rows: int) -> tuple[list[dict], list[str]]:
    """Read exactly a bounded prefix; fail on short/empty/malformed downloads."""
    rows = []
    try:
        reader = csv.reader(lines, strict=True)
        raw_headers = next(reader)
        headers = [header_name(h.lstrip("\ufeff")) for h in raw_headers]
        if not set(FIELDS).issubset(headers) or len(set(headers)) != len(headers):
            raise BatchError("schema_missing_or_colliding_columns")
        indices = {k: headers.index(k) for k in FIELDS}
        for values in reader:
            if len(values) != len(headers):
                raise BatchError("malformed_csv_row", len(rows))
            # Never persist names, phone numbers, street lines, or other unused columns.
            rows.append({k: values[i] for k, i in indices.items()})
            if len(rows) == max_rows:
                return rows, headers
    except (StopIteration, csv.Error, UnicodeError) as exc:
        raise BatchError("malformed_or_empty_csv", len(rows)) from exc
    raise BatchError("incomplete_batch", len(rows))


def scope_for(max_rows: int) -> dict:
    """Prefix membership can shift; this is never a complete national snapshot."""
    return {"selection": "source-order-prefix", "max_rows": max_rows, "fields": list(FIELDS)}


def fixture_batch(path: Path, max_rows: int, max_bytes: int = 8_000_000) -> Batch:
    """Explicit local fixture source, separate from the CMS source in storage and UI."""
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise BatchError("byte_limit")
    try:
        rows, headers = parse_rows(io.StringIO(content.decode("utf-8-sig"), newline=""), max_rows)
    except UnicodeError as exc:
        raise BatchError("malformed_or_empty_csv") from exc
    return Batch(
        rows,
        headers,
        {
            "mode": "fixture",
            "dataset_id": DATASET,
            "release": None,
            "fixture_sha256": hashlib.sha256(content).hexdigest(),
            "retrieval_method": "local_csv_fixture",
        },
        scope_for(max_rows),
    )


def metadata_provenance(meta: dict) -> dict:
    """Resolve only an official CMS CSV resource and retain release fields if supplied."""
    try:
        if meta["identifier"] != DATASET or meta.get("accessLevel") != "public":
            raise ValueError()
        distribution = meta["distribution"][0]
        resource = distribution.get("data", distribution)
        url = resource["downloadURL"]
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "data.cms.gov"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
        ):
            raise ValueError()
        if not parsed.path.startswith("/provider-data/sites/default/files/") or not parsed.path.endswith(
            ".csv"
        ):
            raise ValueError()
        return {
            "mode": "cms",
            "dataset_id": DATASET,
            "metadata_url": METADATA_URL,
            "download_url": url,
            "distribution_id": distribution.get("identifier"),
            "modified": meta.get("modified"),
            "release": meta.get("released"),
            "issued": meta.get("issued"),
            "license": meta.get("license"),
            "access_level": "public",
            "retrieval_method": "bounded_csv_stream",
        }
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise BatchError("metadata_contract") from exc


class CMSConnector:
    def __init__(self, settings: IngestionSettings, transport=None, sleep=time.sleep):
        self.settings, self.transport, self.sleep = settings, transport, sleep
        self.provenance = {}

    def fetch(self) -> Batch:
        """Retry whole reads on transient failures; never combine partial attempts."""
        started = time.monotonic()
        for attempt in range(self.settings.attempts):
            try:
                with httpx.Client(
                    timeout=self.settings.timeout_seconds,
                    follow_redirects=False,
                    transport=self.transport,
                    headers={
                        "User-Agent": "CareRankLab/3.0 educational-registry",
                        "Accept-Encoding": "identity",
                    },
                ) as client:
                    before = self._metadata(client, started)
                    self.provenance = before
                    with client.stream("GET", before["download_url"]) as response:
                        response.raise_for_status()
                        rows, headers = parse_rows(self._lines(response, started), self.settings.max_rows)
                    after = self._metadata(client, started)
                    if before != after:
                        raise BatchError("source_changed_during_download", len(rows))
                    if time.monotonic() - started > self.settings.deadline_seconds:
                        raise BatchError("deadline_exceeded")
                    before["metadata_fingerprint"] = digest(before)
                    return Batch(rows, headers, before, scope_for(self.settings.max_rows))
            except ImportError as exc:
                raise BatchError("http_proxy_dependency_missing") from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status != 429 and status < 500:
                    raise BatchError(f"cms_http_{status}") from exc
                failure = f"cms_http_{status}"
            except httpx.TransportError:
                failure = "cms_transport_failure"
            except BatchError as exc:
                # Truncated transfers may be transient; schema/metadata failures are not.
                if exc.code != "incomplete_batch":
                    raise
                failure = exc.code
            if (
                attempt + 1 == self.settings.attempts
                or time.monotonic() - started >= self.settings.deadline_seconds
            ):
                raise BatchError(failure)
            self.sleep(min(2**attempt, 8))
        raise BatchError("retry_exhausted")

    def _metadata(self, client, started) -> dict:
        """Small, bounded metadata response; response bodies never enter error logs."""
        with client.stream("GET", METADATA_URL) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() - started > self.settings.deadline_seconds:
                    raise BatchError("deadline_exceeded")
                data.extend(chunk)
                if len(data) > 1_000_000:
                    raise BatchError("metadata_byte_limit")
        try:
            return metadata_provenance(json.loads(data))
        except (ValueError, TypeError) as exc:
            raise BatchError("metadata_json") from exc

    def _lines(self, response, started):
        """Bound decoded bytes and elapsed time while preserving quoted CSV newlines."""
        import codecs

        decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        buffered, size = "", 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self.settings.max_bytes:
                raise BatchError("byte_limit")
            if time.monotonic() - started > self.settings.deadline_seconds:
                raise BatchError("deadline_exceeded")
            buffered += decoder.decode(chunk)
            while "\n" in buffered:
                line, buffered = buffered.split("\n", 1)
                yield line + "\n"
        buffered += decoder.decode(b"", final=True)
        if buffered:
            yield buffered

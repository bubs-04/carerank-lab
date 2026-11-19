"""Exercise the real Uvicorn error path without opening a socket or a database."""

import asyncio
import io
import json
import logging
from types import SimpleNamespace
import uuid

import h11
import pytest
from starlette.routing import Route
from uvicorn.protocols.http.h11_impl import RequestResponseCycle

from app.main import app
from app.observability import configure_logging, request_id


@pytest.mark.parametrize("supplied", [str(uuid.uuid4()), "untrusted-request-marker", None])
def test_unexpected_500_keeps_correlation_and_sanitizes_uvicorn(monkeypatch, supplied):
    marker = "harmless-synthetic-exception-marker"

    async def fail(request):
        raise RuntimeError(marker)

    monkeypatch.setattr(app.router, "routes", [*app.router.routes, Route("/_synthetic-error", fail)])
    stream = io.StringIO()
    raw_uvicorn_stream = io.StringIO()
    # Reproduce Uvicorn's independent default handler and restore all logger state.
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        for attribute in ("handlers", "propagate", "disabled", "level"):
            monkeypatch.setattr(logger, attribute, getattr(logger, attribute))
    logging.getLogger("uvicorn").handlers = [logging.StreamHandler(raw_uvicorn_stream)]
    logging.getLogger("uvicorn").propagate = False
    monkeypatch.setattr("sys.stderr", stream)
    configure_logging()

    async def request():
        transport_bytes = []
        conn = h11.Connection(h11.SERVER)
        conn.receive_data(b"GET /_synthetic-error HTTP/1.1\r\nHost: testserver\r\n\r\n")
        assert isinstance(conn.next_event(), h11.Request)
        assert isinstance(conn.next_event(), h11.EndOfMessage)
        event = asyncio.Event()
        event.set()
        headers = [(b"host", b"testserver"), (b"authorization", b"private-header-marker")]
        if supplied:
            headers.append((b"x-request-id", supplied.encode()))
        cycle = RequestResponseCycle(
            scope={
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/_synthetic-error",
                "raw_path": b"/_synthetic-error",
                "root_path": "",
                "query_string": b"token=private-query-marker",
                "headers": headers,
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
            },
            conn=conn,
            transport=SimpleNamespace(write=transport_bytes.append, close=lambda: None),
            flow=SimpleNamespace(write_paused=False, resume_reading=lambda: None),
            logger=logging.getLogger("uvicorn.error"),
            access_logger=logging.getLogger("uvicorn.access"),
            access_log=True,
            default_headers=[],
            message_event=event,
            on_response=lambda: None,
        )
        cycle.more_body = False
        await cycle.run_asgi(app)
        assert cycle.response_complete
        assert request_id.get() is None
        return b"".join(transport_bytes).decode()

    response = asyncio.run(request())
    assert response.startswith("HTTP/1.1 500")
    assert '{"detail":"Internal server error"}' in response
    response_headers = response.split("\r\n\r\n", 1)[0].split("\r\n")[1:]
    correlation = dict(header.split(": ", 1) for header in response_headers)["x-request-id"]
    assert str(uuid.UUID(correlation)) == correlation
    if supplied and len(supplied) == 36:
        assert correlation == supplied
    logs = stream.getvalue()
    assert raw_uvicorn_stream.getvalue() == ""
    assert all(
        secret not in logs + response
        for secret in (marker, "private-query-marker", "private-header-marker", "untrusted-request-marker")
    )
    records = [json.loads(line) for line in logs.splitlines()]
    assert any(record["logger"] == "uvicorn.error" and record["level"] == "ERROR" for record in records)
    http = next(record for record in records if record["event"] == "http_request")
    error = next(record for record in records if record["event"] == "unexpected_http_error")
    assert http["status_code"] == 500
    assert http["request_id"] == error["request_id"] == correlation
    assert error["error_type"] == "RuntimeError"

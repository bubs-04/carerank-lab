"""Bounded structured operational logs. Never serialize requests, SQL or credentials."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import time
import uuid

request_id = ContextVar("request_id", default=None)
execution_id = ContextVar("execution_id", default=None)
attempt_id = ContextVar("attempt_id", default=None)
FIELDS = ("event", "status_code", "method", "route", "duration_ms", "error_type", "worker_id", "instance_id")


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "application_log"),
        }
        for context in (request_id, execution_id, attempt_id):
            value = context.get()
            if value:
                result[context.name] = value
        for key in FIELDS:
            if hasattr(record, key):
                result[key] = getattr(record, key)
        # Existing structured ingestion/monitoring events have a deliberately bounded
        # schema. Keep their identifiers/codes, never arbitrary exception messages.
        try:
            payload = json.loads(record.getMessage())
            if isinstance(payload, dict):
                for key in (
                    "event",
                    "run_id",
                    "mode",
                    "status",
                    "error_code",
                    "exception_type",
                    "reused",
                    "counts",
                ):
                    if key in payload:
                        result[key] = payload[key]
        except (ValueError, TypeError):
            pass
        return json.dumps(result, separators=(",", ":"))


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Uvicorn's default access log includes query strings; use our route-template log.
    logging.getLogger("uvicorn.access").disabled = True


class RequestLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        supplied = dict(scope.get("headers", [])).get(b"x-request-id", b"")
        try:
            correlation = (
                str(uuid.UUID(supplied.decode("ascii"))) if len(supplied) == 36 else str(uuid.uuid4())
            )
        except (ValueError, UnicodeError):
            correlation = str(uuid.uuid4())
        token = request_id.set(correlation)
        started, status = time.monotonic(), 500

        async def correlated_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {
                    **message,
                    "headers": [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                    + [(b"x-request-id", correlation.encode())],
                }
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        finally:
            route = getattr(scope.get("route"), "path", "<unmatched>")
            logging.getLogger("carerank.http").info(
                "http_request",
                extra={
                    "event": "http_request",
                    "method": scope["method"]
                    if scope["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                    else "OTHER",
                    "route": route,
                    "status_code": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            request_id.reset(token)
